#!/usr/bin/env python3
"""B11 offline Self-test regressions (stdlib only)."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SelfTestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='netlab-b11-regression-')
        self.sandbox = Path(self.tmp.name)
        self.livehome = self.sandbox / 'actual-user-home'
        config = self.livehome / 'config'
        config.mkdir(parents=True)
        # These files must not be opened/replaced by self-test even when invalid.
        (config / 'c.conf').write_bytes(b'[general]\ndefault_profile=garbage\n')
        (config / 's.conf').write_bytes(b'[general]\nserver_id=CHANGE_ME\n')
        self.env = dict(os.environ, NETLAB_HOME=str(self.livehome))
        self.before = {p: p.read_bytes() for p in config.iterdir()}

    def tearDown(self):
        self.tmp.cleanup()

    def run_command(self, role, *args, app=ROOT):
        return subprocess.run(['bash', str(app / ('netlab-%s.sh' % role)), 'self-test', *args],
                              env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=25)

    def check_unchanged(self):
        for path, data in self.before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertFalse((self.livehome / 'results').exists())
        self.assertFalse((self.livehome / 'tmp').exists())

    def test_client_entry_all_checks(self):
        p = self.run_command('c', '--non-interactive')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.count('[PASS]'), 9, p.stdout)
        self.assertIn('SELF_TEST PASS (C)', p.stdout)
        self.check_unchanged()

    def test_server_entry_all_checks(self):
        p = self.run_command('s', '--non-interactive')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.count('[PASS]'), 9, p.stdout)
        self.assertIn('SELF_TEST PASS (S)', p.stdout)
        self.check_unchanged()

    def test_quiet_is_compact(self):
        p = self.run_command('c', '--quiet')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(p.stdout.strip().splitlines()), 1, p.stdout)
        self.assertIn('9 checks', p.stdout)
        self.check_unchanged()

    def test_invalid_option_rejected(self):
        for role in ('c', 's'):
            p = self.run_command(role, '--dry-run')
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.check_unchanged()

    def test_missing_component_returns_five(self):
        root = self.sandbox / 'broken-app'
        for folder in ('lib', 'c', 's', 'schemas'):
            (root / folder).mkdir(parents=True, exist_ok=True)
        for name in ('netlab-c.sh', 'netlab-s.sh'):
            shutil.copyfile(ROOT / name, root / name)
        for name in ('common.sh', 'cli.sh', 'menu.sh', 'runner.sh', 'self_test.py',
                     'report.py', 'runner_host.py'):
            shutil.copyfile(ROOT / 'lib' / name, root / 'lib' / name)
        # missing c inventory should fail closed, not touch live home
        p = self.run_command('c', app=root)
        self.assertEqual(p.returncode, 5, p.stdout + p.stderr)
        self.assertIn('SELF_TEST FAIL', p.stderr)
        self.check_unchanged()

    def test_role_not_shared_between_reports(self):
        # Each invocation builds its own isolated fixture; neither run should
        # produce artifacts in the actual user's report directory.
        for role in ('c', 's'):
            p = self.run_command(role, '--quiet', '--non-interactive')
            self.assertEqual(p.returncode, 0, p.stderr)
        self.check_unchanged()


if __name__ == '__main__':
    unittest.main(verbosity=2)
