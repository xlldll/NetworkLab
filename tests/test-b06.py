#!/usr/bin/env python3
"""B06 contract tests. All samples are synthetic. No VPS, SSH, or network tests."""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / 'lib'))
from module_entry import validate_context, InvalidContext, MODULES  # noqa: E402


class B06Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='netlab-b06-')
        self.root = Path(self.temp.name) / 'app'
        shutil.copytree(BASE, self.root, ignore=shutil.ignore_patterns('__pycache__'))
        self.home = Path(self.temp.name) / 'home'
        cfg = self.home / 'config'
        cfg.mkdir(parents=True)
        (cfg / 'c.conf').write_text('[general]\ndefault_profile=standard\n[paths]\ntargets_file=targets.conf\n')
        (cfg / 's.conf').write_text('[general]\nconfig_version=1\nserver_id=lab-vps\ntimezone=UTC+08:00\ndefault_profile=quick\n')
        (cfg / 'targets.conf').write_text('West NAT|nat-us|nat|198.51.100.10||48801|443|us\n')
        self.env = dict(os.environ, NETLAB_HOME=str(self.home))

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, role, *args, env=None):
        return subprocess.run(['bash', str(self.root / ('netlab-' + role + '.sh')), *args],
                              env=env or self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=8)

    def test_all_nine_public_entries_and_internal_guards(self):
        for module_id, (role, _) in MODULES.items():
            with self.subTest(module_id=module_id):
                role_slug = role.lower()
                command = module_id.split('-', 1)[1]
                if command == 'scheduler':
                    command = 'schedule'
                more = (['--target', 'nat-us'] if command in ('paired', 'collect') else [])
                wrapper = self.root / role_slug / (module_id + '.sh')
                public = subprocess.run(['bash', str(wrapper), *more, '--non-interactive']
                                      if command not in ('service', 'schedule') else
                                      ['bash', str(wrapper), 'status' if command == 'service' else 'list'],
                                      env=self.env, stdin=subprocess.DEVNULL,
                                      capture_output=True, text=True, timeout=8)
                self.assertEqual(public.returncode, 8, (module_id, public.stderr))
                self.assertIn('NOT_IMPLEMENTED', public.stderr)
                forged_env = dict(self.env, NETLAB_INTERNAL_WORKER='1')
                private = subprocess.run(['bash', str(wrapper)], env=forged_env,
                                         stdin=subprocess.DEVNULL, capture_output=True,
                                         text=True, timeout=8)
                self.assertEqual(private.returncode, 9, (module_id, private.stderr))
                self.assertIn('SAFETY_BLOCKED', private.stderr)
        self.assertFalse((self.home / 'tmp').exists())
        self.assertFalse((self.home / 'results').exists())

    def test_help_and_public_cli_share_router(self):
        for role, commands in (('c', ['inventory', 'standalone', 'paired', 'proxy', 'collect']),
                               ('s', ['inventory', 'toolbox', 'service', 'schedule'])):
            for command in commands:
                with self.subTest(role=role, command=command):
                    direct = subprocess.run(['bash', str(self.root / role / (role + '-' + ('scheduler' if command == 'schedule' else command) + '.sh')), '--help'],
                                            env=self.env, capture_output=True, text=True,
                                            stdin=subprocess.DEVNULL, timeout=8)
                    cli = self.run_cli(role, command, '--help')
                    self.assertEqual(direct.returncode, 0)
                    self.assertEqual(direct.stdout, cli.stdout)

    def test_dry_run_and_invalid_config_no_results(self):
        p = self.run_cli('c', 'paired', '--target', 'nat-us', '--dry-run')
        self.assertEqual(p.returncode, 8)
        p = self.run_cli('c', 'paired', '--target', 'missing', '--dry-run')
        self.assertEqual(p.returncode, 3)
        p = self.run_cli('s', 'toolbox', '--modules', 'netquality', '--dry-run')
        self.assertEqual(p.returncode, 8)
        self.assertFalse((self.home / 'tmp').exists())

    def create_context(self, module='c-inventory'):
        role, kind = MODULES[module]
        scope = 'nat-us' if module in ('c-paired', 'c-collect') else ('lab-vps' if role == 'S' else 'local')
        rid = '2026-10-22-12-30-00-' + scope
        work = self.home / 'tmp' / ('run-' + rid)
        work.mkdir(parents=True, mode=0o700)
        work.chmod(0o700)
        obj = {
            'contract_version': 1, 'module_id': module, 'role': role,
            'task_kind': kind, 'profile': 'standard', 'run_id': rid,
            'run_uuid': str(uuid.uuid4()), 'correlation_id': None,
            'target_id': 'nat-us' if scope == 'nat-us' else None,
            'server_id': 'lab-vps' if role == 'S' else None,
            'target': {'display_name': 'West NAT', 'ipv4': '198.51.100.10'} if scope == 'nat-us' else None,
            'selected_modules': [], 'non_interactive': True, 'quiet': False,
            'started_at': '2026-10-22T12:30:00+08:00',
            'paths': {'work_dir': str(work), 'result_root': str(self.home / 'results')},
            'effective_parameters': {},
        }
        path = work / 'context.json'
        path.write_text(json.dumps(obj))
        path.chmod(0o600)
        env = dict(self.env, NETLAB_INTERNAL_WORKER='1',
                   NETLAB_WORK_DIR=str(work), NETLAB_CONTEXT_FILE=str(path))
        return obj, path, env

    def assert_blocked(self, module, env):
        p = subprocess.run(['bash', str(self.root / module[0] / (module + '.sh'))],
                           env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=8)
        self.assertEqual(p.returncode, 9, p.stderr)
        self.assertIn('SAFETY_BLOCKED', p.stderr)

    def test_all_nine_valid_synthetic_contexts_return_stub_8(self):
        for module in MODULES:
            with self.subTest(module=module):
                obj, path, env = self.create_context(module)
                self.assertEqual(validate_context(module, env), obj)
                p = subprocess.run(['bash', str(self.root / module[0] / (module + '.sh'))],
                                   env=env, stdin=subprocess.DEVNULL,
                                   capture_output=True, text=True, timeout=8)
                self.assertEqual(p.returncode, 8, p.stderr)
                self.assertIn('NOT_IMPLEMENTED', p.stderr)
                self.assertFalse((self.home / 'results').exists())
                shutil.rmtree(path.parent)

    def test_runner_to_worker_handoff_with_registered_fixture(self):
        # In an isolated test copy only, mark the placeholder as implemented so
        # the existing B05 Runner actually launches the B06 internal entrypoint.
        # It must validate its generated Context and then still return 8.
        wrapper = self.root / 'c' / 'c-inventory.sh'
        original = wrapper.read_text()
        wrapper.write_text(original.replace('# NETLAB_PLACEHOLDER_V1.',
                                            '# NETLAB_IMPLEMENTED_V1 (synthetic fixture).', 1))
        result = self.run_cli('c', 'inventory', '--non-interactive')
        self.assertEqual(result.returncode, 8, result.stderr)
        self.assertIn('NOT_IMPLEMENTED', result.stderr)
        contexts = list((self.home / 'tmp').glob('run-*/context.json'))
        self.assertEqual(len(contexts), 1)
        work = contexts[0].parent
        self.assertEqual(validate_context('c-inventory', {
            'NETLAB_INTERNAL_WORKER': '1', 'NETLAB_CONTEXT_FILE': str(contexts[0]),
            'NETLAB_WORK_DIR': str(work)}).get('module_id'), 'c-inventory')
        self.assertIn('NOT_IMPLEMENTED', (work / 'stderr.log').read_text())
        self.assertFalse((self.home / 'results').exists())

    def test_module_and_role_mismatch_blocked(self):
        obj, path, env = self.create_context()
        obj['role'] = 'S'
        path.write_text(json.dumps(obj))
        self.assert_blocked('c-inventory', env)
        obj['role'] = 'C'
        obj['module_id'] = 'c-proxy'
        path.write_text(json.dumps(obj))
        self.assert_blocked('c-inventory', env)

    def test_path_and_permission_boundaries(self):
        obj, path, env = self.create_context()
        path.chmod(0o644)
        self.assert_blocked('c-inventory', env)
        path.chmod(0o600)
        path.parent.chmod(0o755)
        self.assert_blocked('c-inventory', env)
        path.parent.chmod(0o700)
        env['NETLAB_CONTEXT_FILE'] = str(path.parent / 'other.json')
        self.assert_blocked('c-inventory', env)
        env['NETLAB_CONTEXT_FILE'] = str(path)
        path.rename(path.parent / 'real.json')
        path.symlink_to(path.parent / 'real.json')
        self.assert_blocked('c-inventory', env)

    def test_duplicate_keys_bad_uuid_version_and_timestamp(self):
        obj, path, env = self.create_context()
        path.write_text('{"contract_version":1,"contract_version":1}')
        self.assert_blocked('c-inventory', env)
        for field, value in (('contract_version', 2), ('run_uuid', 'bad'),
                             ('started_at', '2026-10-22T12:30:00Z'),
                             ('run_id', '../other'), ('task_kind', 'management'),
                             ('selected_modules', None), ('non_interactive', 'true')):
            with self.subTest(field=field):
                edited = dict(obj, **{field: value})
                path.write_text(json.dumps(edited))
                self.assert_blocked('c-inventory', env)

    def test_validate_only_is_internal_and_writes_no_report(self):
        _, path, env = self.create_context('s-toolbox')
        command = [sys.executable, '-S', str(self.root / 'lib' / 'module_entry.py'),
                   '--module-id', 's-toolbox', '--validate-only']
        allowed = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        rejected = subprocess.run(command, env=self.env, capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 9, rejected.stderr)
        self.assertFalse((self.home / 'results').exists())

    def test_target_requirement_and_cross_role(self):
        obj, path, env = self.create_context('c-paired')
        obj['target_id'] = None
        path.write_text(json.dumps(obj))
        self.assert_blocked('c-paired', env)
        shutil.rmtree(path.parent)
        obj, path, env = self.create_context('s-inventory')
        obj['server_id'] = 'CHANGE_ME'
        path.write_text(json.dumps(obj))
        self.assert_blocked('s-inventory', env)


if __name__ == '__main__':
    unittest.main(verbosity=2)
