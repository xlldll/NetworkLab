#!/usr/bin/env python3
"""B09 offline tests. Fake worker output is synthetic, never actual network quality."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import report

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


def fake_test(raw='probe.json', value=42, status='completed'):
    return {'test_id': 'probe', 'attempt': 1, 'status': status,
            'evidence_scope': 'local', 'data_provenance': 'observed',
            'tool': {'name': 'synthetic-fixture', 'version': '1.0'},
            'network': {'ip_family': None, 'transport': None, 'direction': 'LOCAL', 'proxy_mode': None},
            'parameters': {'api_token': 'secret_should_be_redacted'},
            'metrics': {'fixture_value': value}, 'raw_files': [raw] if raw else [],
            'errors': [], 'warnings': []}


def fake_handoff(tests=None, raw_files=None, synthetic=True):
    return {'contract_version': 1, 'synthetic': synthetic,
            'requested_tests': ['probe'],
            'tests': [fake_test()] if tests is None else tests,
            'raw_files': [{'path': 'probe.json', 'format': 'json', 'test_id': 'probe'}] if raw_files is None else raw_files,
            'errors': [], 'warnings': []}


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='netlab-b09-')
        self.root = Path(self.tmp.name) / 'app'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('__pycache__'))
        # D01: restore historical placeholder in isolated test copy only.
        stub = (self.root / 's/s-inventory.sh').read_text('utf-8')
        stub = stub.replace('# NETLAB_IMPLEMENTED_V1.', '# NETLAB_PLACEHOLDER_V1.')
        stub = stub.replace('lib/s_inventory.py', 'lib/module_entry.py" --module-id "$NETLAB_MODULE_ID')
        (self.root / 's/s-inventory.sh').write_text(stub, encoding='utf-8')
        # D02: restore C inventory placeholder in this disposable legacy fixture.
        cstub = (self.root / 'c/c-inventory.sh').read_text('utf-8')
        cstub = cstub.replace('# NETLAB_IMPLEMENTED_V1.', '# NETLAB_PLACEHOLDER_V1.')
        cstub = cstub.replace('lib/c_inventory.py', 'lib/module_entry.py" --module-id "$NETLAB_MODULE_ID')
        (self.root / 'c/c-inventory.sh').write_text(cstub, encoding='utf-8')
        self.home = Path(self.tmp.name) / 'home'
        config = self.home / 'config'
        config.mkdir(parents=True)
        (config / 'c.conf').write_text('[general]\nconfig_version=1\ndefault_profile=standard\n[paths]\ntargets_file=targets.conf\n')
        (config / 's.conf').write_text('[general]\nconfig_version=1\nserver_id=lab-vps\ntimezone=UTC+08:00\ndefault_profile=quick\n')
        (config / 'targets.conf').write_text('US NAT|nat-us|nat|198.51.100.12||48801|443|us\n')
        self.env = dict(os.environ, NETLAB_HOME=str(self.home))

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, role, command, *flags, timeout=15):
        return subprocess.run(['bash', str(self.root / ('netlab-%s.sh' % role)), command, *flags],
                              env=self.env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=timeout)

    def worker(self, role='c', module='inventory', handoff=None, raw=b'{"synthetic":true,"value":42}\n',
               code=0, delay=0.0, stdout='', write_handoff=True):
        name = '%s-%s' % (role, module)
        path = self.root / role / (name + '.sh')
        if handoff is None:
            handoff = fake_handoff()
        data = json.dumps(handoff)
        payload = '''#!/usr/bin/env bash
# NETLAB_IMPLEMENTED_V1 (synthetic fixture)
python3 -S - <<'PYWORK'
import os,pathlib,json,time
root=pathlib.Path(os.environ['NETLAB_WORK_DIR'])
raw=root/'raw'
raw.mkdir(mode=0o700)
(raw/'probe.json').write_bytes(%r)
(root/'worker-report.json').write_text(%r, encoding='utf-8')
print(%r)
PYWORK
sleep %s
exit %s
''' % (raw, data, stdout, delay, code)
        if not write_handoff:
            payload = payload.replace("(root/'worker-report.json').write_text(%r, encoding='utf-8')" % data, 'pass')
        path.write_text(payload)
        path.chmod(0o755)
        return path

    def manifests(self):
        return list((self.home / 'results').rglob('*-manifest-*.json'))

    def test_completed_report_and_schema(self):
        self.worker(stdout='probe fixture ok')
        proc = self.cli('c', 'inventory', '--non-interactive')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        paths = self.manifests()
        self.assertEqual(len(paths), 1)
        manifest = report.verify_manifest(paths[0])
        folder = paths[0].parent
        summary = json.loads((folder / next(f['path'] for f in manifest['files'] if f['kind'] == 'summary')).read_text())
        self.assertTrue(manifest['synthetic'] and summary['synthetic'])
        self.assertEqual(manifest['status'], 'completed')
        self.assertEqual(manifest['scope_id'], 'local')
        self.assertEqual(summary['tests'][0]['metrics']['fixture_value'], 42)
        self.assertEqual(summary['tests'][0]['parameters']['api_token'], '[REDACTED]')
        self.assertEqual(len([f for f in manifest['files'] if f['kind'] == 'raw']), 1)
        self.assertTrue(manifest['started_at'].endswith('+08:00'))
        self.assertEqual(manifest['run_uuid'], summary['run_uuid'])
        if Draft202012Validator:
            for kind, obj in (('manifest', manifest), ('summary', summary)):
                schema = json.loads((self.root / 'schemas' / (kind + '.schema.json')).read_text())
                Draft202012Validator(schema).validate(obj)
        # Optional full JSON Schema validation runs when jsonschema is installed.
        # Absence of the optional package does not erase the preceding assertions.

    def test_s_inventory_scope(self):
        self.worker(role='s', module='inventory')
        proc = self.cli('s', 'inventory', '--non-interactive')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest = report.verify_manifest(self.manifests()[0])
        self.assertEqual(manifest['scope_id'], 'lab-vps')
        self.assertEqual(manifest['server_id'], 'lab-vps')
        self.assertIsNone(manifest['target_id'])

    def test_no_report_for_placeholder_and_dry_run(self):
        for role in ('c', 's'):
            self.assertEqual(self.cli(role, 'inventory').returncode, 8)
        self.assertFalse((self.home / 'results').exists())
        self.worker()
        self.assertEqual(self.cli('c', 'inventory', '--dry-run').returncode, 8)
        self.assertFalse((self.home / 'results').exists())

    def test_no_handoff_does_not_fabricate(self):
        self.worker(write_handoff=False)
        proc = self.cli('c', 'inventory', '--non-interactive')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.manifests(), [])

    def test_raw_hash_tamper_is_detected(self):
        self.worker()
        self.assertEqual(self.cli('c', 'inventory').returncode, 0)
        manifest = self.manifests()[0]
        data = json.loads(manifest.read_text())
        rawpath = manifest.parent / next(f['path'] for f in data['files'] if f['kind'] == 'raw')
        rawpath.write_text('tampered\n')
        with self.assertRaises(report.ReportError):
            report.verify_manifest(manifest)

    def test_repeated_runs_unique_ids_no_overwrite(self):
        self.worker()
        for _ in range(2):
            self.assertEqual(self.cli('c', 'inventory').returncode, 0)
        runs = [report.verify_manifest(p) for p in self.manifests()]
        self.assertEqual(len(runs), 2)
        self.assertEqual(len({r['run_uuid'] for r in runs}), 2)
        self.assertEqual(len({r['run_id'] for r in runs}), 2)

    def test_nonzero_exit_keeps_failure_report(self):
        self.worker(code=5)
        proc = self.cli('c', 'inventory')
        self.assertEqual(proc.returncode, 5, proc.stderr)
        m = report.verify_manifest(self.manifests()[0])
        self.assertEqual(m['status'], 'failed')
        self.assertEqual(m['exit_code'], 5)
        self.assertEqual(m['files'][0]['kind'], 'raw')

    def test_worker_lying_about_completion_becomes_partial(self):
        handoff = fake_handoff(tests=[fake_test(status='skipped')])
        self.worker(handoff=handoff)
        p = self.cli('c', 'inventory')
        self.assertEqual(p.returncode, 7, p.stderr)
        m = report.verify_manifest(self.manifests()[0])
        self.assertEqual(m['status'], 'partial')
        self.assertEqual(m['exit_code'], 7)

    def test_invalid_handoff_fails_closed(self):
        handoff = fake_handoff()
        handoff['tests'][0]['raw_files'] = ['missing.json']
        self.worker(handoff=handoff)
        p = self.cli('c', 'inventory')
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertIn('REPORT_ERROR', p.stderr)
        self.assertEqual(self.manifests(), [])
        self.assertEqual(len(list((self.home / 'tmp').glob('run-*/worker-report.json'))), 1)

    def test_symlink_source_rejected(self):
        self.worker()
        p = self.root / 'c' / 'c-inventory.sh'
        text = p.read_text()
        text = text.replace("(raw/'probe.json').write_bytes", "(raw/'probe.json').write_bytes")
        text = text.replace("(root/'worker-report.json').write_text", "(raw/'probe.json').unlink()\n(raw/'probe.json').symlink_to('/etc/hosts')\n(root/'worker-report.json').write_text")
        p.write_text(text)
        res = self.cli('c', 'inventory')
        self.assertEqual(res.returncode, 5, res.stderr)
        self.assertEqual(self.manifests(), [])

    def test_sensitive_stdout_is_redacted(self):
        self.worker(stdout='Authorization: BearerTopSecret api_token=abc123')
        proc = self.cli('c', 'inventory')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        m = report.verify_manifest(self.manifests()[0])
        logs = [f for f in m['files'] if f['kind'] == 'stdout']
        self.assertEqual(len(logs), 1)
        content = (self.manifests()[0].parent / logs[0]['path']).read_text()
        self.assertNotIn('abc123', content)
        self.assertNotIn('BearerTopSecret', content)

    def test_timeout_with_checkpoint(self):
        self.worker(delay=6)
        host = self.root / 'lib' / 'runner_host.py'
        p = subprocess.run([sys.executable, '-S', str(host), '--root', str(self.root),
                            '--role', 'c', '--command', 'inventory', '--module', 'c-inventory',
                            '--non-interactive', '--timeout-seconds', '0.6'],
                           env=self.env, capture_output=True, text=True, timeout=6)
        self.assertEqual(p.returncode, 6, p.stderr)
        m = report.verify_manifest(self.manifests()[0])
        self.assertEqual(m['status'], 'timeout')
        self.assertEqual(m['exit_code'], 6)
        self.assertTrue(m['synthetic'])

    def test_ctrl_c_checkpoint(self):
        self.worker(delay=8)
        proc = subprocess.Popen(['bash', str(self.root / 'netlab-c.sh'), 'inventory', '--non-interactive'],
                                env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not list((self.home / 'tmp').glob('run-*/worker-report.json')):
                time.sleep(.03)
            self.assertTrue(list((self.home / 'tmp').glob('run-*/worker-report.json')))
            time.sleep(.15)
            os.killpg(proc.pid, signal.SIGINT)
            out, err = proc.communicate(timeout=6)
            self.assertEqual(proc.returncode, 130, (out, err))
            manifest = report.verify_manifest(self.manifests()[0])
            self.assertEqual(manifest['status'], 'interrupted')
            self.assertEqual(manifest['exit_code'], 130)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()

    def test_no_overwrite_or_symlink_result_root(self):
        self.worker()
        actual = Path(self.tmp.name) / 'real-results'
        actual.mkdir()
        shortcut = Path(self.tmp.name) / 'linked-results'
        shortcut.symlink_to(actual)
        p = self.cli('c', 'inventory', '--output-dir', str(shortcut))
        self.assertEqual(p.returncode, 5)
        self.assertFalse(list(actual.iterdir()))

    def test_raw_directory_symlink_rejected(self):
        self.worker()
        path = self.root / 'c' / 'c-inventory.sh'
        text = path.read_text().replace(
            "(root/'worker-report.json').write_text",
            "raw.rename(root/'raw-private')\n"
            "raw.symlink_to(root/'raw-private', target_is_directory=True)\n"
            "(root/'worker-report.json').write_text",
        )
        path.write_text(text)
        p = self.cli('c', 'inventory')
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertEqual(self.manifests(), [])

    def test_duplicate_json_keys_rejected(self):
        self.worker(raw=b'{"a":1,"a":2}\n')
        p = self.cli('c', 'inventory')
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertEqual(self.manifests(), [])

    def test_raw_name_path_traversal_rejected(self):
        handoff = fake_handoff(raw_files=[{'path': '../secrets.txt', 'format': 'txt', 'test_id': 'probe'}])
        self.worker(handoff=handoff)
        p = self.cli('c', 'inventory')
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertEqual(self.manifests(), [])

    def test_unchanged_raw_bytes(self):
        original = b'{"data": 17}\n'
        self.worker(raw=original)
        p = self.cli('c', 'inventory')
        self.assertEqual(p.returncode, 0, p.stderr)
        m = report.verify_manifest(self.manifests()[0])
        raw_name = next(f['path'] for f in m['files'] if f['kind'] == 'raw')
        self.assertEqual((self.manifests()[0].parent / raw_name).read_bytes(), original)

    def test_binary_and_ndjson_formats(self):
        for format_, name, raw in (('binary', 'probe.json', b'\x00\xff\xfe'),
                                   ('ndjson', 'probe.json', b'{"a":1}\n{"b":2}\n')):
            with self.subTest(format=format_):
                handoff = fake_handoff(raw_files=[{'path': name, 'format': format_, 'test_id': 'probe'}])
                self.worker(handoff=handoff, raw=raw)
                p = self.cli('c', 'inventory')
                self.assertEqual(p.returncode, 0, p.stderr)
                reports = [report.verify_manifest(p) for p in self.manifests()]
                self.assertTrue(any(m['files'][0]['format'] == format_ for m in reports))


if __name__ == '__main__':
    unittest.main(verbosity=2)
