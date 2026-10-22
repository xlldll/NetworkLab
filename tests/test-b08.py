#!/usr/bin/env python3
"""B08 isolated Server config tests; no network, real timers or VPS services."""
import importlib.util
import os
import pty
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('server_config', ROOT / 'lib' / 'server_config.py')
sys.path.insert(0, str(ROOT / 'lib'))
import server_config as sc
import config_manager as cm
TEMPLATE = (ROOT / 'defaults' / 's.conf').read_text(encoding='utf-8')
GOOD = TEMPLATE.replace('server_id = CHANGE_ME', 'server_id = nat-us')


class ServerConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='netlab-b08-')
        self.home = Path(self.temp.name) / 'home'
        self.conf = self.home / 'config'
        self.conf.mkdir(parents=True, mode=0o700)
        self.path = self.conf / 's.conf'
        self.path.write_text(GOOD, encoding='utf-8')
        self.env = dict(os.environ, NETLAB_HOME=str(self.home))

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args):
        return subprocess.run(['bash', str(ROOT / 'netlab-s.sh'), *args],
                              env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=8)

    def test_template_placeholder_rejected(self):
        self.path.write_text(TEMPLATE)
        p = self.cli('config', 'validate')
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn('server_id', p.stderr)

    def test_validate_and_profile_outputs(self):
        p = self.cli('config', 'validate')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('nat-us', p.stdout)
        p = self.cli('config', 'profiles')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('[quick]', p.stdout)
        self.assertIn('[standard] (default)', p.stdout)
        self.assertIn('[deep]', p.stdout)
        self.assertIn('0=no metered allowance', p.stdout)
        self.assertFalse((self.home / 'results').exists())

    def test_unknown_keys_sections_duplicates(self):
        for bad in (
            GOOD + '\n[evil]\na = b\n',
            GOOD.replace('config_version = 1', 'config_version = 1\nother = 123'),
            GOOD.replace('config_version = 1', 'config_version = 1\nconfig_version = 1'),
            GOOD + '\n[tool.unknown]\nenabled = true\n',
            GOOD.replace('netquality = normal', 'netquality = turbo'),
            GOOD.replace('server_id = nat-us', 'server_id = CHANGE_ME'),
            GOOD.replace('timezone = UTC+08:00', 'timezone = local'),
            GOOD.replace('config_version = 1', 'config_version = 2'),
        ):
            with self.subTest(bad=bad[-55:]):
                self.path.write_text(bad)
                self.assertEqual(self.cli('config', 'validate').returncode, 3)

    def test_override_inheritance_and_tool_disable(self):
        self.path.write_text(GOOD.replace('profile_override = inherit', 'profile_override = quick', 1))
        model, _ = sc.load(self.path)
        res = sc.effective_profile(model, 'deep')
        self.assertEqual(res['hardwarequality']['mode'], 'off')
        self.assertEqual(res['hardwarequality']['effective_profile'], 'quick')
        self.assertEqual(res['netquality']['mode'], 'full')
        self.path.write_text(GOOD.replace('[tool.hardwarequality]\nenabled = true', '[tool.hardwarequality]\nenabled = false'))
        model, _ = sc.load(self.path)
        self.assertEqual(sc.effective_profile(model, 'deep')['hardwarequality']['mode'], 'off')

    def test_optional_tool_defaults_and_warnings(self):
        basic = '[general]\nconfig_version=1\nserver_id=nat-us\ntimezone=UTC+08:00\n'
        self.path.write_text(basic)
        model, warnings = sc.load(self.path)
        self.assertEqual(model['default_profile'], 'standard')
        self.assertEqual(model['profiles']['quick']['hardwarequality'], 'off')
        self.assertEqual(model['profiles']['standard']['netquality'], 'normal')
        self.assertTrue(warnings)

    def test_limits_and_scheduler_validation(self):
        for bad in (
            GOOD.replace('max_metered_mb_per_run = 0', 'max_metered_mb_per_run = -1'),
            GOOD.replace('max_metered_mb_per_day = 0', 'max_metered_mb_per_day = unlimited'),
            GOOD.replace('time = 20:30', 'time = 25:88'),
            GOOD.replace('days = daily', 'days = mon,mon'),
            GOOD.replace('profile = standard\nmodules', 'profile = ultra\nmodules'),
            GOOD.replace('modules = inventory,netquality,tcpquality', 'modules = inventory,inventory'),
            GOOD.replace('modules = inventory,netquality,tcpquality', 'modules = inventory,foo'),
        ):
            with self.subTest(bad=bad[-50:]):
                self.path.write_text(bad)
                self.assertEqual(self.cli('config', 'validate').returncode, 3)
        self.path.write_text(GOOD.replace('days = daily', 'days = mon,tue,wed'))
        self.assertEqual(self.cli('config','validate').returncode, 0)

    def test_enabled_schedule_does_not_create_timer(self):
        self.path.write_text(GOOD.replace('enabled = false\ntime', 'enabled = true\ntime'))
        p = self.cli('config', 'validate')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('NOT create timers', p.stderr)
        self.assertFalse((self.home / 'results').exists())
        self.assertFalse((self.home / 'tmp').exists())
        self.assertFalse((self.home / 'logs').exists())

    def test_override_config_file_and_no_effects(self):
        alt = self.conf / 'custom.ini'
        alt.write_text(GOOD.replace('server_id = nat-us', 'server_id = alt-vps'))
        p = self.cli('config', 'validate', '--config', str(alt))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('alt-vps', p.stdout)
        self.assertIn('nat-us', self.path.read_text())
        self.assertEqual(self.cli('config', 'validate', '--config', '/not/existing/s.conf').returncode, 3)

    def test_edit_non_tty_dry_run_and_symlink(self):
        old = self.path.read_bytes()
        self.assertEqual(self.cli('config', 'edit', '--editor', 'nano').returncode, 2)
        p = self.cli('config', 'edit', '--editor', 'nano', '--dry-run')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('DRY_RUN', p.stdout)
        self.assertEqual(old, self.path.read_bytes())
        original = self.conf / 'original.conf'
        original.write_bytes(old)
        self.path.unlink()
        self.path.symlink_to(original)
        self.assertEqual(self.cli('config', 'validate').returncode, 9)
        self.assertEqual(self.cli('config', 'edit', '--editor', 'nano', '--dry-run').returncode, 9)

    def test_editor_atomic_rollback_backup(self):
        # Deterministic fake editor under PTY; no human editor interaction.
        binary = Path(self.temp.name) / 'bin'
        binary.mkdir()
        script = binary / 'nano'
        env = dict(self.env, PATH=str(binary) + os.pathsep + self.env.get('PATH', ''))
        master, slave = pty.openpty()
        original = self.path.read_bytes()
        try:
            script.write_text('#!/bin/sh\nprintf "\\n[invalid]\\nx=y\\n" >> "$1"\n')
            script.chmod(0o755)
            p = subprocess.run(['bash', str(ROOT/'netlab-s.sh'), 'config', 'edit', '--editor', 'nano'],
                               stdin=slave, stdout=slave, stderr=slave, env=env, timeout=8)
            self.assertEqual(p.returncode, 3)
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(len(list(self.conf.glob('.s.conf.backup-*'))), 0)
            script.write_text('#!/bin/sh\nsed -i.bak "s/server_id = nat-us/server_id = new-vps/" "$1"\n')
            p = subprocess.run(['bash', str(ROOT/'netlab-s.sh'), 'config', 'edit', '--editor', 'nano'],
                               stdin=slave, stdout=slave, stderr=slave, env=env, timeout=8)
            self.assertEqual(p.returncode, 0)
            self.assertIn('server_id = new-vps', self.path.read_text())
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
            backups = list(self.conf.glob('.s.conf.backup-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
        finally:
            os.close(slave)
            os.close(master)

    def test_editor_can_repair_invalid_existing_file(self):
        self.path.write_text(GOOD.replace('server_id = nat-us', 'server_id = CHANGE_ME'))
        binary = Path(self.temp.name) / 'bin'
        binary.mkdir()
        script = binary / 'vim'
        script.write_text('#!/bin/sh\nsed -i.bak "s/server_id = CHANGE_ME/server_id = fixed-vps/" "$1"\n')
        script.chmod(0o755)
        env = dict(self.env, PATH=str(binary) + os.pathsep + self.env.get('PATH',''))
        master, slave = pty.openpty()
        try:
            p = subprocess.run(['bash', str(ROOT/'netlab-s.sh'), 'config','edit','--editor','vim'],
                               stdin=slave,stdout=slave,stderr=slave,env=env,timeout=8)
            self.assertEqual(p.returncode, 0)
            self.assertEqual(self.cli('config','validate').returncode, 0)
        finally:
            os.close(slave)
            os.close(master)

    def test_runner_context_contains_effective_s_settings(self):
        # A test-only worker confirms Context includes the evaluated profiles;
        # no real measurement program is run or installed.
        import shutil
        worker = ROOT / 's' / 's-toolbox.sh'
        with tempfile.TemporaryDirectory(prefix='netlab-b08-app-') as root_dir:
            app = Path(root_dir) / 'app'
            shutil.copytree(ROOT, app, ignore=shutil.ignore_patterns('__pycache__'))
            entry = app / 's' / 's-toolbox.sh'
            entry.write_text('''#!/usr/bin/env bash
# NETLAB_IMPLEMENTED_V1 (test fixture only)
python3 -S - <<'PYWORK'
import json, os
from pathlib import Path
ctx = json.loads(Path(os.environ['NETLAB_CONTEXT_FILE']).read_text())
cfg = ctx['effective_parameters']['server_config']
assert cfg['tool_modes']['netquality']['mode'] == 'full'
assert cfg['tool_modes']['hardwarequality']['mode'] == 'off'
assert cfg['limits']['max_metered_mb_per_run'] == 0
assert ctx['server_id'] == 'nat-us'
PYWORK
''')
            entry.chmod(0o755)
            self.path.write_text(GOOD.replace('profile_override = inherit', 'profile_override = quick', 1))
            p = subprocess.run(['bash', str(app / 'netlab-s.sh'), 'toolbox', '--profile', 'deep', '--non-interactive'],
                               env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertFalse((self.home/'results').exists())

    def test_runner_uses_b08_validation_and_context(self):
        self.path.write_text(GOOD.replace('time = 20:30', 'time = 28:30'))
        self.assertEqual(self.cli('inventory','--non-interactive').returncode, 3)
        self.assertFalse((self.home/'tmp').exists())
        self.path.write_text(GOOD)
        p = self.cli('inventory','--non-interactive')
        self.assertEqual(p.returncode, 8, p.stderr)
        self.assertFalse((self.home/'tmp').exists())
        p = self.cli('toolbox','--modules','netquality','--profile','deep','--non-interactive')
        self.assertEqual(p.returncode, 8, p.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
