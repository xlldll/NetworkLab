#!/usr/bin/env python3
"""B05 Runner integration without any external connectivity or actual benchmarks."""
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

BASE = Path(__file__).resolve().parent.parent


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='netlab-b05-')
        self.root = Path(self.temp.name) / 'app'
        shutil.copytree(BASE, self.root, ignore=shutil.ignore_patterns('__pycache__'))
        self.home = Path(self.temp.name) / 'home'
        config = self.home / 'config'
        config.mkdir(parents=True)
        (config / 'c.conf').write_text('[general]\nconfig_version=1\ndefault_profile=standard\n[paths]\ntargets_file=targets.conf\n')
        (config / 's.conf').write_text('[general]\nconfig_version=1\nserver_id=lab-vps\ntimezone=UTC+08:00\ndefault_profile=quick\n')
        (config / 'targets.conf').write_text('West NAT|nat-us|nat|198.51.100.12||48801|443|us\n')
        self.env = dict(os.environ, NETLAB_HOME=str(self.home))

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, role, *args, timeout=12):
        return subprocess.run(['bash', str(self.root / ('netlab-%s.sh' % role)), *args],
                              env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)

    def test_public_entry_and_direct_module(self):
        # B05 checks historical placeholders in an isolated application copy.
        # Never launch D01/D02 real inventory as a synthetic routing fixture.
        for role in ('c', 's'):
            stub = self.root / role / (role + '-inventory.sh')
            stub.write_text(
                '#!/usr/bin/env bash\n'
                '# B05 isolated placeholder fixture (no implemented marker)\n'
                'exec bash "$(dirname "$0")/../netlab-' + role + '.sh" inventory "$@"\n',
                encoding='utf-8')
        for role, module in (('c', 'inventory'), ('s', 'inventory'), ('c', 'proxy'), ('s', 'toolbox')):
            with self.subTest(role=role, module=module):
                p = self.cli(role, module, '--non-interactive')
                self.assertEqual(p.returncode, 8, p.stderr)
                self.assertIn('NOT_IMPLEMENTED', p.stderr)
                direct = subprocess.run(['bash', str(self.root / role / ('%s-%s.sh' % (role, module))), '--non-interactive'],
                                        env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
                self.assertEqual(direct.returncode, 8, direct.stderr)
        s = self.cli('s', 'schedule', 'list')
        self.assertEqual(s.returncode, 8)
        self.assertFalse((self.home / 'tmp').exists())
        self.assertFalse((self.home / 'results').exists())

    def test_help_and_version_without_config(self):
        shutil.rmtree(self.home / 'config')
        for role in ('c', 's'):
            self.assertEqual(self.cli(role, '--help').returncode, 0)
            self.assertEqual(self.cli(role, '--version').returncode, 0)
            self.assertEqual(self.cli(role, 'inventory', '--help').returncode, 0)

    def test_config_preflight_and_missing_target(self):
        self.assertEqual(self.cli('c', 'paired', '--target', 'nat-us', '--non-interactive').returncode, 8)
        wrong = self.cli('c', 'paired', '--target', 'unknown', '--non-interactive')
        self.assertEqual(wrong.returncode, 3)
        self.assertIn('CONFIG_ERROR', wrong.stderr)
        self.assertEqual(self.cli('c', 'paired', '--profile', 'not-a-mode', '--target', 'nat-us').returncode, 2)
        self.assertEqual(self.cli('c', 'paired', '--non-interactive').returncode, 2)
        self.assertEqual(self.cli('s', 'toolbox', '--modules', 'bogus').returncode, 2)
        (self.home / 'config' / 's.conf').write_text('[general]\nserver_id=CHANGE_ME\n')
        self.assertEqual(self.cli('s', 'inventory').returncode, 3)
        self.assertFalse((self.home / 'tmp').exists())

    def test_bad_target_file(self):
        target = self.home / 'config' / 'targets.conf'
        target.write_text('Bad|nat-us|nat|999.999.999.999||48801|443|us\n')
        self.assertEqual(self.cli('c', 'paired', '--target', 'nat-us', '--non-interactive').returncode, 3)
        target.write_text('Good|nat-us|nat|198.51.100.12||48801|443|us\nGood|nat-us|nat|198.51.100.12||48801|443|us\n')
        self.assertEqual(self.cli('c', 'paired', '--target', 'nat-us', '--non-interactive').returncode, 3)

    def test_dry_run_no_workspace(self):
        for role, command in [('c', 'inventory'), ('s', 'toolbox')]:
            p = self.cli(role, command, '--dry-run')
            self.assertEqual(p.returncode, 8, p.stderr)
            self.assertFalse((self.home / 'tmp').exists())

    def install_fake_worker(self, role='c', module='inventory', body=''):
        path = self.root / role / ('%s-%s.sh' % (role, module))
        # A fixture, NOT a real NetworkLab benchmark.
        path.write_text('#!/usr/bin/env bash\n# NETLAB_IMPLEMENTED_V1 (test fixture only)\n' + body + '\n')
        path.chmod(0o755)
        return path

    def test_mock_worker_context_and_no_fake_report(self):
        self.install_fake_worker(body='''python3 -S - <<'PYWORK'
import json,os,pathlib,stat
p=pathlib.Path(os.environ['NETLAB_CONTEXT_FILE'])
a=json.loads(p.read_text())
assert a['role']=='C' and a['module_id']=='c-inventory'
assert a['run_uuid'] and a['started_at'].endswith('+08:00')
assert stat.S_IMODE(p.stat().st_mode)==0o600
assert stat.S_IMODE(p.parent.stat().st_mode)==0o700
(pathlib.Path(os.environ['NETLAB_WORK_DIR'])/'worker-ok.txt').write_text('done')
PYWORK''')
        p = self.cli('c', 'inventory', '--non-interactive')
        self.assertEqual(p.returncode, 0, p.stderr)
        runs = list((self.home / 'tmp').glob('run-*/context.json'))
        self.assertEqual(len(runs), 1)
        obj = json.loads(runs[0].read_text())
        self.assertEqual(obj['task_kind'], 'measurement')
        self.assertEqual(obj['target'], None)
        self.assertFalse((self.home / 'results').exists())

    def test_worker_nonzero_code_preserved(self):
        self.install_fake_worker(body='echo "worker error" >&2\nexit 7')
        p = self.cli('c', 'inventory', '--non-interactive')
        self.assertEqual(p.returncode, 7)
        self.assertIn('worker error', p.stderr)
        logs = list((self.home / 'tmp').glob('run-*/stderr.log'))
        self.assertEqual(len(logs), 1)
        self.assertIn('worker error', logs[0].read_text())

    def test_watchdog_timeout_and_owned_child_cleanup(self):
        self.install_fake_worker(body='echo before-timeout\nsleep 12 &\nchild=$!\necho "$child" > "$NETLAB_WORK_DIR/child.pid"\nwait "$child"')
        host = self.root / 'lib' / 'runner_host.py'
        p = subprocess.run(['python3', '-S', str(host), '--root', str(self.root), '--role', 'c',
                            '--command', 'inventory', '--module', 'c-inventory',
                            '--non-interactive', '--timeout-seconds', '0.4'],
                           env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 6, (p.stdout, p.stderr))
        self.assertIn('TIMEOUT', p.stderr)
        self.assertIn('before-timeout', p.stdout)
        pidfiles = list((self.home / 'tmp').glob('run-*/child.pid'))
        self.assertEqual(len(pidfiles), 1)
        # On Linux a stopped descendant may briefly appear as a zombie; it must not run.
        pid = int(pidfiles[0].read_text())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            proc_stat = Path('/proc/%s/stat' % pid)
            if proc_stat.exists():
                self.assertEqual(proc_stat.read_text().split()[2], 'Z')

    def test_signal_interrupt_propagates(self):
        self.install_fake_worker(body='echo started\nsleep 10')
        proc = subprocess.Popen(['bash', str(self.root / 'netlab-c.sh'), 'inventory', '--non-interactive'],
                                env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
        try:
            # Do not signal during Python's interpreter startup. Wait for the worker
            # Context to exist before exercising the Runner's SIGINT handler.
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline and not list((self.home / 'tmp').glob('run-*/context.json')):
                time.sleep(0.03)
            self.assertTrue(list((self.home / 'tmp').glob('run-*/context.json')))
            time.sleep(0.15)
            os.killpg(proc.pid, signal.SIGINT)
            out, err = proc.communicate(timeout=4)
            self.assertEqual(proc.returncode, 130, (proc.returncode, out, err))
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()


if __name__ == '__main__':
    unittest.main(verbosity=2)
