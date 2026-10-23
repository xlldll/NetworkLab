#!/usr/bin/env python3
"""C05 isolated report-integrity and failure-boundary acceptance (Python 3.8+).

IMPORTANT: All measurement records are synthetic. A private copy of NetworkLab
replaces all 9 workers with inert files, then ONLY an explicit synthetic fixture
is activated. No network, services, cron, sudo, or real user data are touched.
"""
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

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'lib'))
import report

PROBES = ('curl', 'wget', 'iperf3', 'mtr', 'nexttrace', 'ping', 'ssh', 'traceroute',
          'flent', 'netquality', 'tcpquality')


def synthetic_test(status='completed', raw_file='probe.json'):
    return {'test_id': 'probe', 'attempt': 1, 'status': status,
            'evidence_scope': 'local', 'data_provenance': 'observed',
            'tool': {'name': 'c05-synthetic', 'version': '1'},
            'network': {'ip_family': None, 'transport': None, 'direction': 'LOCAL', 'proxy_mode': None},
            'parameters': {'api_token': 'C05_PRIVATE_TOKEN'},
            'metrics': {'fixture': 17}, 'raw_files': [raw_file] if raw_file else [],
            'errors': [], 'warnings': []}


def synthetic_handoff(status='completed', format_='json'):
    return {'contract_version': 1, 'synthetic': True, 'requested_tests': ['probe'],
            'tests': [synthetic_test(status=status)],
            'raw_files': [{'path': 'probe.json', 'format': format_, 'test_id': 'probe'}],
            'errors': [], 'warnings': []}


def private_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class C05Tests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(prefix='networklab-c05-')
        self.base = Path(self.t.name)
        self.stage = self.base / 'stage'
        self.stage.mkdir(mode=0o700)
        for name in ('c', 's', 'lib', 'defaults', 'schemas'):
            shutil.copytree(REPO / name, self.stage / name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ('netlab-c.sh', 'netlab-s.sh'):
            shutil.copy2(REPO / name, self.stage / name)
        for role in ('c', 's'):
            for module in (self.stage / role).glob('*.sh'):
                module.write_text('#!/usr/bin/env bash\n# INERT C05 test placeholder\nexit 8\n', encoding='utf-8')
                module.chmod(0o700)
        self.home = self.base / 'HOME'
        self.home.mkdir(mode=0o700)
        self.nl = self.home / '.networklab'
        cfg = self.nl / 'config'
        cfg.mkdir(mode=0o700, parents=True)
        (cfg / 'c.conf').write_text('[general]\nconfig_version=1\ndefault_profile=standard\n'
                                    '[paths]\ntargets_file=targets.conf\n', encoding='utf-8')
        (cfg / 's.conf').write_text('[general]\nconfig_version=1\nserver_id=c05-server\n'
                                    'timezone=UTC+08:00\ndefault_profile=standard\n', encoding='utf-8')
        (cfg / 'targets.conf').write_text('', encoding='utf-8')
        # Fail closed if any probe command is accidentally invoked by a fixture.
        self.fakebin = self.base / 'fakebin'
        self.fakebin.mkdir(mode=0o700)
        self.marker = self.base / 'UNEXPECTED_LIVE_PROBE'
        for name in PROBES:
            fake = self.fakebin / name
            fake.write_text('#!/bin/sh\nprintf "UNEXPECTED" >> "$NETLAB_C05_PROBE_MARKER"\nexit 98\n')
            fake.chmod(0o700)
        self.env = dict(os.environ, HOME=str(self.home), NETLAB_HOME=str(self.nl),
                        NETLAB_C05_PROBE_MARKER=str(self.marker),
                        PATH=str(self.fakebin) + os.pathsep + os.environ.get('PATH', '/usr/bin:/bin'))
        for key in ('PYTHONPATH', 'PYTHONHOME', 'NETLAB_INTERNAL_WORKER',
                    'NETLAB_CONTEXT_FILE', 'NETLAB_WORK_DIR', 'NETLAB_LOG_FILE'):
            self.env.pop(key, None)
        self.assertFalse((self.nl / 'results').exists())

    def tearDown(self):
        try:
            self.assertFalse(self.marker.exists(), 'live probe command was invoked')
        finally:
            self.t.cleanup()

    def fixture(self, *, role='c', code=0, handoff=None, raw=b'{"synthetic": true, "seq": 17}\n',
                sleep=0, write_handoff=True, bad_handoff=None, extra='', stdout=''):
        if handoff is None:
            handoff = synthetic_handoff()
        path = self.stage / role / ('%s-inventory.sh' % role)
        script = '''#!/usr/bin/env bash
# NETLAB_IMPLEMENTED_V1; synthetic fixture ONLY
python3 -S - <<'C05_PY'
import os,pathlib
work=pathlib.Path(os.environ['NETLAB_WORK_DIR'])
raw_dir=work/'raw'
raw_dir.mkdir(mode=0o700)
(raw_dir/'probe.json').write_bytes(%r)
%s
%s
print(%r)
C05_PY
sleep %s
exit %s
''' % (raw,
       "(work/'worker-report.json').write_bytes(%r)" % (
           bad_handoff if bad_handoff is not None else json.dumps(handoff).encode('utf-8'))
       if write_handoff else 'pass', extra, stdout, sleep, code)
        path.write_text(script, encoding='utf-8')
        path.chmod(0o700)

    def run_cli(self, role='c', *args, timeout=12):
        return subprocess.run(['bash', str(self.stage / ('netlab-%s.sh' % role))] + list(args),
                              env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)

    def run_internal(self, role='c', timeout_seconds=0.5):
        return subprocess.run([sys.executable, '-S', str(self.stage / 'lib/runner_host.py'),
                               '--root', str(self.stage), '--role', role,
                               '--command', 'inventory', '--module', role+'-inventory',
                               '--non-interactive', '--timeout-seconds', str(timeout_seconds)],
                              env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=12)

    def manifests(self):
        if not (self.nl / 'results').exists():
            return []
        return list((self.nl / 'results').rglob('*-manifest-*.json'))

    def workspaces(self):
        return list((self.nl / 'tmp').glob('run-*')) if (self.nl / 'tmp').exists() else []

    def published(self, expected_code=0, role='c'):
        proc = self.run_cli(role, 'inventory', '--non-interactive')
        self.assertEqual(proc.returncode, expected_code, proc.stderr)
        self.assertEqual(len(self.manifests()), 1, proc.stdout + proc.stderr)
        manifest = report.verify_manifest(self.manifests()[0])
        self.assertTrue(manifest['synthetic'])
        return manifest

    def results_show(self, manifest, role='c'):
        return self.run_cli(role, 'results', 'show', manifest['run_id'])

    def test_c_and_s_completed_reports_are_verifiable(self):
        for role in ('c', 's'):
            with self.subTest(role=role):
                self.fixture(role=role)
                obj = self.published(role=role)
                self.assertEqual(obj['status'], 'completed')
                self.assertEqual(obj['exit_code'], 0)
                self.assertEqual(obj['role'], role.upper())
                self.assertIn('VERIFIED', self.results_show(obj, role).stdout)
                self.assertTrue(obj['started_at'].endswith('+08:00'))
                self.assertFalse(any('C05_PRIVATE_TOKEN' in p.read_text('utf-8', errors='ignore')
                                     for p in self.manifests()))
                # Each role receives distinct sandbox state for deterministic counts.
                shutil.rmtree(self.nl / 'results')

    def test_missing_handoff_means_no_official_report(self):
        self.fixture(write_handoff=False)
        p = self.run_cli('c', 'inventory', '--non-interactive')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.manifests(), [])
        self.assertTrue(self.workspaces())

    def test_malformed_handoff_fails_and_keeps_workspace(self):
        self.fixture(bad_handoff=b'{"contract_version": 1, "tests": [')
        p = self.run_cli('c', 'inventory', '--non-interactive')
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertIn('REPORT_ERROR', p.stderr)
        self.assertEqual(self.manifests(), [])
        self.assertTrue(any((w/'worker-report.json').is_file() for w in self.workspaces()))

    def test_invalid_json_raw_rejected_without_manifest(self):
        self.fixture(raw=b'{"unfinished":')
        p = self.run_cli('c', 'inventory')
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertFalse(self.manifests())
        self.assertTrue(any((w/'raw/probe.json').is_file() for w in self.workspaces()))

    def test_invalid_ndjson_rejected_without_manifest(self):
        self.fixture(raw=b'{"valid":1}\n{"invalid":\n', handoff=synthetic_handoff(format_='ndjson'))
        p = self.run_cli('c', 'inventory')
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertEqual(self.manifests(), [])

    def test_raw_symlink_rejected(self):
        self.fixture(extra="(raw_dir/'probe.json').unlink()\n(raw_dir/'probe.json').symlink_to('/etc/hosts')")
        p = self.run_cli('c', 'inventory')
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertIn('REPORT_ERROR', p.stderr)
        self.assertTrue(any((w/'worker-report.json').is_file() for w in self.workspaces()))
        self.assertFalse(self.manifests())

    def test_raw_hardlink_rejected(self):
        self.fixture(extra="other=work/'same-inode.json'\n"
                           "other.write_bytes(b'{\\\"test\\\":true}\\n')\n"
                           "(raw_dir/'probe.json').unlink()\n"
                           "os.link(str(other), str(raw_dir/'probe.json'))")
        p = self.run_cli('c', 'inventory')
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertIn('REPORT_ERROR', p.stderr)
        self.assertTrue(any((w/'worker-report.json').is_file() for w in self.workspaces()))
        self.assertEqual(self.manifests(), [])

    def test_result_root_symlink_rejected_without_outside_write(self):
        self.fixture()
        outside = self.base / 'outside'
        outside.mkdir()
        link = self.base / 'linked'
        link.symlink_to(outside, target_is_directory=True)
        p = self.run_cli('c', 'inventory', '--output-dir', str(link))
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertFalse(list(outside.iterdir()))
        self.assertEqual(self.manifests(), [])

    def test_failure_exit_keeps_status_and_raw(self):
        self.fixture(code=5)
        m = self.published(5)
        self.assertEqual((m['status'], m['exit_code']), ('failed', 5))
        self.assertTrue(any(f['kind']=='raw' for f in m['files']))

    def test_completed_exit_with_skipped_test_becomes_partial(self):
        self.fixture(handoff=synthetic_handoff(status='skipped'))
        m = self.published(7)
        self.assertEqual((m['status'], m['exit_code']), ('partial', 7))

    def test_timeout_with_checkpoint_keeps_valid_report(self):
        self.fixture(sleep=7)
        p = self.run_internal(timeout_seconds=0.45)
        self.assertEqual(p.returncode, 6, p.stderr)
        self.assertEqual(len(self.manifests()), 1)
        m = report.verify_manifest(self.manifests()[0])
        self.assertEqual((m['status'], m['exit_code']), ('timeout', 6))
        self.assertTrue(self.workspaces())

    def test_timeout_without_checkpoint_keeps_private_evidence_only(self):
        self.fixture(write_handoff=False, sleep=7)
        p = self.run_internal(timeout_seconds=0.45)
        self.assertEqual(p.returncode, 6, p.stderr)
        self.assertEqual(self.manifests(), [])
        self.assertTrue(self.workspaces())

    def interrupt(self, with_checkpoint):
        self.fixture(sleep=8, write_handoff=with_checkpoint)
        proc = subprocess.Popen(['bash', str(self.stage / 'netlab-c.sh'), 'inventory', '--non-interactive'],
                                env=self.env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if with_checkpoint:
                    ready = any((w/'worker-report.json').is_file() for w in self.workspaces())
                else:
                    ready = any((w/'raw/probe.json').is_file() for w in self.workspaces())
                if ready:
                    break
                if proc.poll() is not None:
                    break
                time.sleep(.025)
            self.assertTrue(ready, 'fixture never reached its checkpoint boundary')
            time.sleep(.12)
            os.killpg(proc.pid, signal.SIGINT)
            out, err = proc.communicate(timeout=8)
            self.assertEqual(proc.returncode, 130, (out, err))
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)

    def test_sigint_with_checkpoint_keeps_interrupted_report(self):
        self.interrupt(True)
        self.assertEqual(len(self.manifests()), 1)
        m = report.verify_manifest(self.manifests()[0])
        self.assertEqual((m['status'], m['exit_code']), ('interrupted', 130))

    def test_sigint_without_checkpoint_keeps_private_data_only(self):
        self.interrupt(False)
        self.assertEqual(self.manifests(), [])
        self.assertTrue(self.workspaces())

    def test_raw_file_tampering_rejected_by_browser(self):
        self.fixture()
        obj = self.published()
        entry = next(f for f in obj['files'] if f['kind']=='raw')
        raw_file = self.manifests()[0].parent/entry['path']
        raw_file.write_bytes(b'CORRUPTED DATA')
        with self.assertRaises(report.ReportError):
            report.verify_manifest(self.manifests()[0])
        show = self.results_show(obj)
        self.assertEqual(show.returncode, 5, show.stdout + show.stderr)

    def test_summary_file_tampering_rejected_by_browser(self):
        self.fixture()
        obj = self.published()
        entry = next(f for f in obj['files'] if f['kind']=='summary')
        (self.manifests()[0].parent/entry['path']).write_bytes(b'{}\n')
        self.assertEqual(self.results_show(obj).returncode, 5)

    def test_manifest_invalid_json_is_not_trusted(self):
        self.fixture()
        obj = self.published()
        self.manifests()[0].write_bytes(b'{ BROKEN')
        listing = self.run_cli('c', 'results', 'list')
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertIn('INVALID', listing.stdout)
        self.assertEqual(self.results_show(obj).returncode, 5)

    def test_indexed_file_symlink_is_rejected(self):
        self.fixture()
        obj = self.published()
        entry = next(f for f in obj['files'] if f['kind']=='raw')
        raw_file = self.manifests()[0].parent/entry['path']
        original = raw_file.read_bytes()
        raw_file.unlink()
        outside = self.base/'foreign'
        outside.write_bytes(original)
        raw_file.symlink_to(outside)
        self.assertEqual(self.results_show(obj).returncode, 5)

    def test_parallel_like_runs_have_unique_identity_and_no_overwrite(self):
        self.fixture()
        for _ in range(2):
            p = self.run_cli('c', 'inventory', '--non-interactive')
            self.assertEqual(p.returncode, 0, p.stderr)
        manifests = self.manifests()
        self.assertEqual(len(manifests), 2)
        objects = [report.verify_manifest(m) for m in manifests]
        self.assertEqual(len({m['run_uuid'] for m in objects}), 2)
        self.assertEqual(len({m['run_id'] for m in objects}), 2)
        self.assertEqual(len({m.name for m in manifests}), 2)

    def test_failed_manifest_publish_is_not_listed_and_leaves_orphans(self):
        """Fault injection after raw and summary: no Manifest => no trusted Run.

        Explicitly documents CURRENT limitation: raw/summary orphan files are not
        automatically repaired or garbage-collected by B09.
        """
        from unittest.mock import patch
        # First produce a standard private Context and synthetic worker data but
        # omit handoff, to avoid automatic report publication during Runner exit.
        self.fixture(write_handoff=False)
        p = self.run_cli('c', 'inventory')
        self.assertEqual(p.returncode, 0, p.stderr)
        work = self.workspaces()[0]
        context = json.loads((work/'context.json').read_text('utf-8'))
        (work/'worker-report.json').write_text(json.dumps(synthetic_handoff()), encoding='utf-8')
        original = report._publish_bytes
        def faulty_publisher(data, dest):
            if '-manifest-' in dest.name:
                raise report.ReportError('C05 injected manifest publish crash')
            return original(data, dest)
        with patch.object(report, '_publish_bytes', side_effect=faulty_publisher):
            with self.assertRaisesRegex(report.ReportError, 'injected'):
                report.finalize(context, work, 0, time.monotonic())
        self.assertFalse(self.manifests(), 'no committed manifest should be visible')
        result_files = list((self.nl/'results').rglob('*'))
        self.assertTrue(any(f.is_file() and '-summary-' in f.name for f in result_files),
                        'current writer leaves orphan summary from interrupted publication')
        self.assertFalse(any(f.is_file() and '.netlab-stage-' in f.name for f in result_files),
                         'temporary staging files must have been removed')
        self.assertFalse(any(f.is_file() and f.name.startswith('.netlab-reservation-') for f in result_files),
                         'reservation should be released')
        list_result = self.run_cli('c', 'results', 'list')
        self.assertEqual(list_result.returncode, 0)
        self.assertIn('No reports found', list_result.stdout)
        # A future distinct Run must still succeed; do not retry the same run_id.
        self.fixture()
        p2 = self.run_cli('c', 'inventory')
        self.assertEqual(p2.returncode, 0, p2.stderr)
        self.assertEqual(len(self.manifests()), 1)

    def test_report_source_is_not_modified(self):
        before = {p: private_sha(REPO/p) for p in ('lib/report.py', 'lib/runner_host.py', 'lib/result_browser.py')}
        self.fixture(stdout='C05 synthetic')
        self.published()
        self.assertEqual(before, {p: private_sha(REPO/p) for p in before})


if __name__ == '__main__':
    if sys.version_info < (3, 8):
        print('[C05] ERROR Python 3.8+ required', file=sys.stderr)
        sys.exit(4)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(C05Tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print('\n[C05] PASS: %s isolated report/failure/recovery checks; host=%s; synthetic only.' %
              (result.testsRun, sys.platform))
        print('[C05] NOTE: orphan file recovery, cross-run cryptographic authentication, and live probes are NOT implemented.')
    sys.exit(0 if result.wasSuccessful() else 1)
