#!/usr/bin/env python3
"""B12 installer tests; all filesystem mutations confined to temporary homes."""
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class B12Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='netlab-b12-')
        self.base = Path(self.tmp.name)
        self.home = self.base / 'userhome'
        self.home.mkdir()
        self.lab = self.home / '.networklab'
        self.env = dict(os.environ, HOME=str(self.home), NETLAB_HOME=str(self.lab))

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, *args, source=ROOT, env=None, timeout=40):
        return subprocess.run(['sh', str(source / 'install.sh'), *args],
                              cwd=source, env=env or self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)

    def checked_install(self, *args, source=ROOT, env=None):
        p = self.install(*args, source=source, env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def launch(self, role, *args, env=None):
        return subprocess.run([str(self.lab / 'bin' / ('netlab-' + role)), *args],
                              env=env or self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=20)

    def test_dry_run_creates_nothing(self):
        p = self.checked_install('--role', 'c', '--dry-run')
        self.assertIn('DRY_RUN', p.stdout)
        self.assertFalse(self.lab.exists())

    def test_c_first_install_configs_command_and_permissions(self):
        p = self.checked_install('--role', 'c', '--skip-self-test')
        self.assertIn('c.conf, targets.conf', p.stdout)
        for name in ('app/netlab-c.sh', 'config/c.conf', 'config/targets.conf', 'bin/netlab-c'):
            self.assertTrue((self.lab / name).is_file(), name)
        self.assertFalse((self.lab / 'config/s.conf').exists())
        for name in ('config/c.conf', 'config/targets.conf'):
            self.assertEqual(stat.S_IMODE((self.lab / name).stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.lab / 'config').stat().st_mode), 0o700)
        p = self.launch('c', 'config', 'validate')
        self.assertEqual(p.returncode, 0, p.stderr)
        p = self.launch('c', 'targets', 'validate')
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_s_init_unique_server_id_and_validates(self):
        self.checked_install('--role', 's', '--skip-self-test')
        text = (self.lab / 'config/s.conf').read_text()
        self.assertRegex(text, r'server_id = s-[0-9a-f]{16}\n')
        self.assertNotRegex(text, r'(?m)^server_id = CHANGE_ME$')
        self.assertFalse((self.lab / 'config/c.conf').exists())
        p = self.launch('s', 'config', 'validate')
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_preserve_configs_reports_existing_code_and_server_id(self):
        self.checked_install('--role', 's', '--skip-self-test')
        config = self.lab / 'config/s.conf'
        before = config.read_bytes()
        evidence = self.lab / 'results' / 'keep-me.txt'
        evidence.write_bytes(b'private-history')
        appdoc = self.lab / 'app' / 'docs' / 'keep-me.txt'
        appdoc.write_bytes(b'private-app-note')
        p = self.checked_install('--role', 's', '--skip-self-test')
        self.assertIn('app [preserved]', p.stdout)
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(evidence.read_bytes(), b'private-history')
        self.assertEqual(appdoc.read_bytes(), b'private-app-note')

    def test_both_roles_can_install_without_clobbering_other_role(self):
        self.checked_install('--role', 'c', '--skip-self-test')
        self.checked_install('--role', 's', '--skip-self-test')
        for file in ('config/c.conf', 'config/targets.conf', 'config/s.conf',
                     'bin/netlab-c', 'bin/netlab-s'):
            self.assertTrue((self.lab / file).is_file(), file)

    def test_default_auto_linux_selects_server(self):
        if sys.platform != 'linux':
            self.skipTest('Linux-only auto role test')
        p = self.checked_install('--skip-self-test')
        self.assertIn('INSTALL PASS: S', p.stdout)
        self.assertTrue((self.lab / 'config/s.conf').exists())

    def test_default_placement_under_home_local_bin(self):
        env = dict(self.env)
        env.pop('NETLAB_HOME')
        p = self.checked_install('--role', 'c', '--skip-self-test', env=env)
        self.assertIn(str(self.home / '.local/bin/netlab-c'), p.stdout)
        self.assertTrue((self.home / '.local/bin/netlab-c').exists())
        self.assertFalse((self.home / '.zshrc').exists())

    def test_bin_collision_refused_and_unmodified(self):
        (self.lab / 'bin').mkdir(parents=True)
        target = self.lab / 'bin/netlab-c'
        target.write_bytes(b'#!/bin/sh\necho user-owned\n')
        p = self.install('--role', 'c', '--skip-self-test')
        self.assertEqual(p.returncode, 9, p.stdout + p.stderr)
        self.assertEqual(target.read_bytes(), b'#!/bin/sh\necho user-owned\n')

    def test_existing_non_executable_launcher_rejected(self):
        self.checked_install('--role', 'c', '--skip-self-test')
        launcher = self.lab / 'bin/netlab-c'
        launcher.chmod(0o600)
        p = self.install('--role', 'c', '--skip-self-test')
        self.assertEqual(p.returncode, 9, p.stdout + p.stderr)
        self.assertEqual(stat.S_IMODE(launcher.stat().st_mode), 0o600)

    def test_symlinked_config_parent_refused(self):
        outside = self.base / 'outside'
        outside.mkdir()
        self.lab.mkdir()
        (self.lab / 'config').symlink_to(outside, target_is_directory=True)
        p = self.install('--role', 'c', '--skip-self-test')
        self.assertEqual(p.returncode, 9, p.stdout + p.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_netlab_home_refused(self):
        actual = self.base / 'actual'
        actual.mkdir()
        self.lab.symlink_to(actual, target_is_directory=True)
        p = self.install('--role', 'c', '--skip-self-test')
        self.assertEqual(p.returncode, 9, p.stdout + p.stderr)
        self.assertEqual(list(actual.iterdir()), [])

    def test_invalid_existing_server_config_not_replaced(self):
        path = self.lab / 'config'
        path.mkdir(parents=True)
        config = path / 's.conf'
        config.write_text('[general]\nserver_id = CHANGE_ME\n')
        before = config.read_bytes()
        p = self.install('--role', 's', '--skip-self-test')
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(config.read_bytes(), before)

    def test_invalid_arguments_rejected(self):
        for args in (('--role', 'both'), ('--role',), ('--nonsense',),
                     ('--bin-dir', 'relative/bin')):
            p = self.install(*args)
            self.assertEqual(p.returncode, 2, (args, p.stdout, p.stderr))
        self.assertFalse(self.lab.exists())

    def test_quoted_path_launcher_works(self):
        self.lab = self.home / "custom one's networklab"
        env = dict(self.env, NETLAB_HOME=str(self.lab))
        self.checked_install('--role', 'c', '--skip-self-test', env=env)
        p = self.launch('c', '--version', env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_full_offline_self_test_c_and_s(self):
        p = self.checked_install('--role', 'c')
        self.assertIn('SELF_TEST PASS (C): 9 checks', p.stdout)
        p = self.checked_install('--role', 's')
        self.assertIn('SELF_TEST PASS (S): 9 checks', p.stdout)
        self.assertFalse((self.lab / 'results/c').exists())
        self.assertFalse((self.lab / 'results/s').exists())

    def test_broken_source_rejected_without_side_effects(self):
        bad = self.base / 'badsource'
        bad.mkdir()
        (bad / 'install.sh').write_bytes((ROOT / 'install.sh').read_bytes())
        (bad / 'lib').mkdir()
        (bad / 'lib/installer.py').write_bytes((ROOT / 'lib/installer.py').read_bytes())
        p = self.install('--role', 'c', source=bad)
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertFalse(self.lab.exists())

    def test_symlink_in_source_refused(self):
        fake = self.base / 'fake'
        shutil.copytree(ROOT, fake)
        (fake / 'docs' / 'evil.txt').symlink_to('/etc/passwd')
        p = self.install('--role', 'c', source=fake)
        self.assertEqual(p.returncode, 9, p.stdout + p.stderr)
        self.assertFalse(self.lab.exists())

    def test_no_code_overwrite_on_reinstall(self):
        self.checked_install('--role', 'c', '--skip-self-test')
        script = self.lab / 'app' / 'netlab-c.sh'
        script.write_bytes(script.read_bytes() + b'\n# preserved on B12 re-install\n')
        self.checked_install('--role', 'c', '--skip-self-test')
        self.assertTrue(script.read_bytes().endswith(b'# preserved on B12 re-install\n'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
