#!/usr/bin/env python3
"""C07 synthetic positive/negative release audit cases; no remote requests."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/release_audit.py'
spec = importlib.util.spec_from_file_location('release_audit', str(SCRIPT))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
TAG = 'v' + mod.get_version((ROOT / 'lib/common.sh').read_text('utf-8'))
EXPECTED = TAG[1:]
DIFFERENT_TAG = 'v' + '.'.join(EXPECTED.split('.')[:2] + [str(int(EXPECTED.split('.')[2]) + 1)])


def make_zip(entries, wrapped=False):
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
        for name, data in entries:
            name = ('NetworkLab/' + name) if wrapped else name
            zipf.writestr(name, data)
    return result.getvalue()


def fixture_files():
    return [(name, (ROOT / name).read_bytes()) for name in mod.REQUIRED + mod.WORKERS]


def create_assets(folder, blob, tag=TAG, valid_sidecar=True):
    arc = folder / ('networklab-' + tag + '.zip')
    side = folder / (arc.name + '.sha256')
    arc.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    if not valid_sidecar:
        digest = '0' * 64
    side.write_text(digest + '  ' + arc.name + '\n', encoding='ascii')
    return arc, side


class C07Tests(unittest.TestCase):
    def test_source_gate_and_version(self):
        self.assertEqual(mod.audit_source(ROOT), EXPECTED)

    def test_cli_default_offline(self):
        p = subprocess.run([sys.executable, '-B', str(SCRIPT)], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('PASS: read-only release audit', p.stdout)

    def test_readme_rejects_corrupt_placeholder(self):
        with self.assertRaisesRegex(mod.AuditError, 'README'):
            mod.validate_readme('# NetworkLab\n343 43 43 4 ' * 18)

    def test_version_parser_rejects_missing_or_invalid(self):
        for bad in ("NETLAB_VERSION='abc'", "NETLAB_VERSION='0.1.1' # fake", ''):
            with self.subTest(bad=bad), self.assertRaises(mod.AuditError):
                mod.get_version(bad)

    def test_release_flat_archive(self):
        with tempfile.TemporaryDirectory(prefix='netlab-c07-') as d:
            zipfile_, sha = create_assets(Path(d), make_zip(fixture_files()))
            self.assertEqual(mod.audit_assets(zipfile_, sha, TAG), EXPECTED)

    def test_release_wrapped_archive(self):
        with tempfile.TemporaryDirectory(prefix='netlab-c07-') as d:
            zipfile_, sha = create_assets(Path(d), make_zip(fixture_files(), wrapped=True))
            self.assertEqual(mod.audit_assets(zipfile_, sha, TAG), EXPECTED)

    def test_bad_checksum_fails(self):
        with tempfile.TemporaryDirectory(prefix='netlab-c07-') as d:
            zipfile_, sha = create_assets(Path(d), make_zip(fixture_files()), valid_sidecar=False)
            with self.assertRaisesRegex(mod.AuditError, 'SHA-256 mismatch'):
                mod.audit_assets(zipfile_, sha, TAG)

    def test_bad_sidecar_filename_fails(self):
        with tempfile.TemporaryDirectory(prefix='netlab-c07-') as d:
            zipfile_, sha = create_assets(Path(d), make_zip(fixture_files()))
            sha.write_text('a' * 64 + '  other.zip\n', encoding='ascii')
            with self.assertRaisesRegex(mod.AuditError, 'filename mismatch'):
                mod.audit_assets(zipfile_, sha, TAG)

    def test_tag_version_mismatch_fails(self):
        with tempfile.TemporaryDirectory(prefix='netlab-c07-') as d:
            zipfile_, sha = create_assets(Path(d), make_zip(fixture_files()), tag=DIFFERENT_TAG)
            with self.assertRaisesRegex(mod.AuditError, 'Release Tag differs'):
                mod.audit_assets(zipfile_, sha, DIFFERENT_TAG)

    def test_missing_required_release_file_fails(self):
        items = [(n, b) for n, b in fixture_files() if n != 'lib/updater.py']
        with self.assertRaisesRegex(mod.AuditError, 'missing required file'):
            mod.inspect_zip(make_zip(items), TAG)

    def test_path_traversal_rejected(self):
        items = fixture_files() + [('../bad.sh', b'bad')]
        with self.assertRaisesRegex(mod.AuditError, 'path traversal'):
            mod.inspect_zip(make_zip(items), TAG)

    def test_symlink_member_rejected(self):
        f = io.BytesIO()
        with zipfile.ZipFile(f, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in fixture_files():
                z.writestr(name, data)
            info = zipfile.ZipInfo('linked')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, 'secret')
        with self.assertRaisesRegex(mod.AuditError, 'symlink/special'):
            mod.inspect_zip(f.getvalue(), TAG)

    def test_duplicate_casefold_path_rejected(self):
        items = fixture_files() + [('LIB/COMMON.SH', b'bad')]
        with self.assertRaisesRegex(mod.AuditError, 'duplicate/case-colliding'):
            mod.inspect_zip(make_zip(items), TAG)

    def test_private_artifact_rejected(self):
        for bad in ('.networklab/config/c.conf', '.git/HEAD', 'tests/__pycache__/foo.pyc'):
            with self.subTest(name=bad), self.assertRaisesRegex(mod.AuditError, 'private artifacts'):
                mod.inspect_zip(make_zip(fixture_files() + [(bad, b'bad')]), TAG)

    def test_broken_readme_in_zip_rejected(self):
        items = [(n, b'# NetworkLab\n343 43 43 4'*20 if n == 'README.md' else b)
                 for n, b in fixture_files()]
        with self.assertRaisesRegex(mod.AuditError, 'README'):
            mod.inspect_zip(make_zip(items), TAG)

    def test_skeleton_worker_cannot_claim_implemented(self):
        items = [(n, b'NETLAB_IMPLEMENTED_V1\n' if n == 's/s-toolbox.sh' else b)
                 for n, b in fixture_files()]
        with self.assertRaisesRegex(mod.AuditError, 'unexpectedly marked implemented'):
            mod.inspect_zip(make_zip(items), TAG)

    def test_cli_requires_pinned_tag_and_asset_pair(self):
        for args in (['--online'], ['--asset', 'example.zip'],
                     ['--tag', 'latest', '--online']):
            with self.subTest(args=args):
                p = subprocess.run([sys.executable, '-B', str(SCRIPT)] + args,
                                   capture_output=True, text=True, timeout=10)
                self.assertNotEqual(p.returncode, 0)

    def test_source_gate_checks_all_worker_markers(self):
        # Test pure worker guard, without overwriting repository source.
        with tempfile.TemporaryDirectory(prefix='netlab-c07-') as d:
            p = Path(d)
            for name in mod.REQUIRED + mod.WORKERS:
                dest = p / name
                dest.parent.mkdir(exist_ok=True, parents=True)
                shutil.copy2(str(ROOT / name), str(dest))
            worker = p / 'c/c-paired.sh'
            worker.write_bytes(b'NETLAB_IMPLEMENTED_V1\n' + worker.read_bytes())
            with self.assertRaisesRegex(mod.AuditError, 'unexpectedly marked implemented'):
                mod.audit_source(p)

    def test_version_source_is_semver_and_dynamic(self):
        # Never hardcode the release version: next tagged release must still test.
        s = (ROOT / 'lib/common.sh').read_text('utf-8')
        self.assertEqual(mod.get_version(s), EXPECTED)
        self.assertRegex(TAG, r'^v\d+\.\d+\.\d+$')

    def test_asset_cli_with_pinned_tag(self):
        with tempfile.TemporaryDirectory(prefix='netlab-c07-') as d:
            arc, sha = create_assets(Path(d), make_zip(fixture_files()))
            p = subprocess.run([sys.executable, '-B', str(SCRIPT),
                                '--asset', str(arc), '--checksum', str(sha),
                                '--tag', TAG], cwd=str(ROOT),
                               capture_output=True, text=True, timeout=20)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('local Release asset + SHA-256', p.stdout)

    def test_online_nonofficial_repo_blocked_without_network(self):
        with self.assertRaisesRegex(mod.AuditError, 'official repository'):
            mod.audit_online(ROOT, TAG, 'other/NetworkLab')


if __name__ == '__main__':
    unittest.main(verbosity=2)
