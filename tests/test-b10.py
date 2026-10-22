#!/usr/bin/env python3
"""B10 offline result/log browser regression tests using B09's synthetic fixture."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('b09_fixture', ROOT / 'tests' / 'test-b09.py')
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixture_module.ReportTests('test_completed_report_and_schema')
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.root = self.fx.root
        self.home = self.fx.home
        self.env = self.fx.env

    def cli(self, role, *args, env=None):
        return subprocess.run(['bash', str(self.root / ('netlab-' + role + '.sh')), *args],
                              env=(env or self.env), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=15)

    def make_c_report(self, **kwargs):
        self.fx.worker(**kwargs)
        p = self.cli('c', 'inventory', '--non-interactive')
        self.assertEqual(p.returncode, 0, p.stderr)
        return self.fx.manifests()[-1]

    def get_run_id(self, path):
        return json.loads(path.read_text())['run_id']

    def test_empty_results_and_logs_do_not_need_config(self):
        (self.home / 'config' / 'c.conf').unlink()
        for role in ('c', 's'):
            for cmd in (('results', 'list'), ('logs', 'list')):
                p = self.cli(role, *cmd)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn('No ', p.stdout)
        self.assertFalse((self.home / 'results').exists())

    def test_list_and_show_real_report_identity_and_hash(self):
        m = self.make_c_report()
        rid = self.get_run_id(m)
        p = self.cli('c', 'results', 'list')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(rid, p.stdout)
        self.assertIn('UNVERIFIED', p.stdout)
        p = self.cli('c', 'results', 'show', rid)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('VERIFIED', p.stdout)
        self.assertIn('SYNTHETIC / NOT REAL MEASUREMENT', p.stdout)
        self.assertIn('probe #1: completed', p.stdout)

    def test_limit_and_newest_first(self):
        self.fx.worker()
        for _ in range(3):
            self.assertEqual(self.cli('c', 'inventory').returncode, 0)
        p = self.cli('c', 'results', 'list', '--limit', '2')
        rows = [r for r in p.stdout.splitlines() if r.startswith('20')]
        self.assertEqual(len(rows), 2, p.stdout)
        p = self.cli('c', 'results', 'list', '--limit', '1', '--quiet')
        self.assertEqual(len(p.stdout.splitlines()), 1, p.stdout)

    def test_s_reports_are_not_c_reports(self):
        self.fx.worker(role='s', module='inventory')
        self.assertEqual(self.cli('s', 'inventory').returncode, 0)
        self.assertIn('lab-vps', self.cli('s', 'results', 'list').stdout)
        self.assertIn('No reports', self.cli('c', 'results', 'list').stdout)

    def test_summary_tamper_fails_in_show(self):
        m = self.make_c_report()
        obj = json.loads(m.read_text())
        summary = next(x['path'] for x in obj['files'] if x['kind'] == 'summary')
        (m.parent / summary).write_text('not the same data')
        p = self.cli('c', 'results', 'show', obj['run_id'])
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertIn('integrity check failed', p.stderr)

    def test_raw_tamper_fails_in_show(self):
        m = self.make_c_report()
        obj = json.loads(m.read_text())
        raw = next(x['path'] for x in obj['files'] if x['kind'] == 'raw')
        (m.parent / raw).write_text('tampered')
        self.assertEqual(self.cli('c', 'results', 'show', obj['run_id']).returncode, 5)

    def test_not_found_and_path_traversal_rejected(self):
        self.assertEqual(self.cli('c', 'results', 'show', '../etc/passwd').returncode, 2)
        self.assertEqual(self.cli('c', 'results', 'show', '2026-10-22-00-00-00-local').returncode, 5)
        self.assertEqual(self.cli('c', 'results', 'show', '/tmp/manifest.json').returncode, 2)

    def test_logs_list_includes_published_stdout_and_local_logs(self):
        self.make_c_report(stdout='safe fixture stdout')
        logdir = self.home / 'logs'
        logdir.mkdir()
        (logdir / 'netlab.log').write_text('safe fixture log')
        p = self.cli('c', 'logs', 'list')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('run-stdout', p.stdout)
        self.assertIn('netlab.log', p.stdout)
        self.assertNotIn('safe fixture stdout', p.stdout)
        self.assertNotIn('safe fixture log', p.stdout)

    def test_log_symlink_is_not_listed(self):
        logdir = self.home / 'logs'
        logdir.mkdir()
        (logdir / 'bad.log').symlink_to('/etc/hosts')
        self.assertNotIn('bad.log', self.cli('c', 'logs', 'list').stdout)

    def test_symlink_results_root_is_rejected(self):
        actual = self.home / 'real'
        actual.mkdir()
        shortcut = self.home / 'linked'
        shortcut.symlink_to(actual, target_is_directory=True)
        p = self.cli('c', 'results', 'list', '--output-dir', str(shortcut))
        self.assertEqual(p.returncode, 5, p.stderr)

    def test_symlink_scope_ignored(self):
        root = self.home / 'results' / 'c'
        root.mkdir(parents=True)
        (root / 'bad-scope').symlink_to(self.home / 'config', target_is_directory=True)
        p = self.cli('c', 'results', 'list')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('No reports', p.stdout)

    def test_bad_manifest_displayed_as_invalid(self):
        folder = self.home / 'results' / 'c' / 'local'
        folder.mkdir(parents=True)
        (folder / 'c-manifest-local-2026-10-22-00-00-00.json').write_text('{malformed')
        p = self.cli('c', 'results', 'list')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('INVALID', p.stdout)

    def test_output_dir_override_and_no_file_creation(self):
        override = self.home / 'elsewhere'
        override.mkdir()
        for role in ('c', 's'):
            p = self.cli(role, 'results', 'list', '--output-dir', str(override))
            self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(list(override.iterdir()), [])

    def test_wrong_scope_copy_does_not_make_run_ambiguous(self):
        m = self.make_c_report()
        rid = self.get_run_id(m)
        alt = self.home / 'results' / 'c' / 'other'
        alt.mkdir()
        (alt / m.name).write_bytes(m.read_bytes())
        # This copy must not count as a valid second report: folder scope mismatch.
        p = self.cli('c', 'results', 'show', rid)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_working_directory_logs_without_final_report(self):
        tmp = self.home / 'tmp' / 'run-2026-10-22-00-00-00-local'
        tmp.mkdir(parents=True)
        (tmp / 'stderr.log').write_text('api_token=private_not_to_print')
        p = self.cli('c', 'logs', 'list')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('work-stderr', p.stdout)
        self.assertIn('stderr.log', p.stdout)
        self.assertNotIn('private_not_to_print', p.stdout)

    def test_bad_timezone_report_is_invalid_header(self):
        m = self.make_c_report()
        obj = json.loads(m.read_text())
        obj['started_at'] = obj['started_at'].replace('+08:00', '+00:00')
        m.write_text(json.dumps(obj))
        p = self.cli('c', 'results', 'list')
        self.assertIn('INVALID', p.stdout)

    def test_unindexed_bogus_files_not_listed(self):
        folder = self.home / 'results' / 'c' / 'local'
        folder.mkdir(parents=True)
        (folder / 'secrets.txt').write_text('not a manifest')
        self.assertIn('No reports', self.cli('c', 'results', 'list').stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
