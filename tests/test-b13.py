#!/usr/bin/env python3
"""B13 offline release/rollback tests. Never access the public network."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('netlab_updater', ROOT / 'lib/updater.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def archive(version='v0.1.1', broken=False, wrapping=False):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w', zipfile.ZIP_DEFLATED) as z:
        for base, ds, fs in os.walk(ROOT):
            ds[:] = [d for d in ds if d not in ('__pycache__', '.git')]
            for name in fs:
                file = Path(base) / name
                if file.is_symlink():
                    continue
                rel = file.relative_to(ROOT).as_posix()
                if rel.endswith('.pyc'):
                    continue
                content = file.read_bytes()
                if rel == 'lib/common.sh':
                    content, count = re.subn(rb"(?m)^NETLAB_VERSION='[^']+'$",
                                             ("NETLAB_VERSION='%s'" % version.lstrip('v')).encode('ascii'),
                                             content)
                    if count != 1:
                        raise AssertionError('release fixture must declare exactly one version')
                if broken and rel == 'lib/self_test.py':
                    content = b'raise SystemExit(5)\n'
                z.writestr(('NetworkLab/' if wrapping else '') + rel, content)
    return bio.getvalue()


class B13Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='netlab-b13-')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.home = self.path / 'home'
        self.env = dict(os.environ, NETLAB_HOME=str(self.home), HOME=str(self.path))
        p = subprocess.run(['sh', str(ROOT/'install.sh'), '--role', 'c', '--skip-self-test'], env=self.env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=40)
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        self.app = self.home/'app'
        # Simulate a v0.1.0 installation even if the checked-out source is
        # v0.1.1 or later. An actual upgrade must occur in lifecycle tests.
        base = self.app / 'lib/common.sh'
        previous = base.read_bytes()
        previous, count = re.subn(rb"(?m)^NETLAB_VERSION='[^']+'$",
                                  b"NETLAB_VERSION='0.1.0'", previous)
        self.assertEqual(count, 1, 'installed fixture version must be unique')
        base.write_bytes(previous)
        self.assertEqual(updater.app_version(self.app), 'v0.1.0')
        (self.home/'config/update-source.json').write_text(json.dumps({'github_repo': 'example/NetworkLab'}))
        (self.home/'config/update-source.json').chmod(0o600)
        self.original = (self.app/'lib/common.sh').read_bytes()
        self.saved = self.home/'results/keep.txt'
        self.saved.write_bytes(b'keep reports')
        self.saved_config = (self.home/'config/c.conf').read_bytes()

    def run_cli(self, *args, role='c'):
        return subprocess.run(['bash', str(ROOT / ('netlab-%s.sh' % role)), *args], env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=25)

    def run_main(self, action='apply', tag='v0.1.1', dry_run=False):
        argv = ['--root', str(ROOT), '--role', 'c', '--action', action]
        if action == 'apply': argv += ['--version', tag]
        if dry_run: argv += ['--dry-run']
        with mock.patch.dict(os.environ, self.env):
            return updater.main(argv)

    def remote(self, zipcontent=None, tag='v0.1.1', checksum=None):
        data = zipcontent if zipcontent is not None else archive(version=tag)
        name = 'networklab-%s.zip' % tag
        base = 'https://github.com/example/NetworkLab/releases/download/%s/' % tag
        meta = {'tag_name': tag, 'draft': False, 'prerelease': False, 'assets': [
            {'name': name, 'browser_download_url': base+name},
            {'name': name+'.sha256', 'browser_download_url': base+name+'.sha256'}]}
        digest = checksum if checksum is not None else hashlib.sha256(data).hexdigest()
        sidecar = (digest + '  ' + name + '\n').encode()
        return mock.patch.object(updater, 'release_metadata', return_value=meta), mock.patch.object(
            updater, 'url_bytes', side_effect=lambda url, max_bytes: sidecar if url.endswith('.sha256') else data)

    def verify_untouched(self):
        self.assertEqual(self.original, (self.app/'lib/common.sh').read_bytes())
        self.assertEqual(self.saved.read_bytes(), b'keep reports')
        self.assertEqual(self.saved_config, (self.home/'config/c.conf').read_bytes())

    def test_01_cli_public_routes_and_missing_source(self):
        self.assertEqual(self.run_cli('update', 'apply', '--version', 'v0.1.1', '--dry-run').returncode, 0)
        self.assertIn('DRY_RUN', self.run_cli('update','apply','--version','v0.1.1','--dry-run').stdout)
        self.assertEqual(self.run_cli('update','apply').returncode, 2)
        self.assertEqual(self.run_cli('update','apply','--version','nonsense').returncode, 2)
        (self.home/'config/update-source.json').unlink()
        self.assertEqual(self.run_cli('update','check').returncode, 3)

    def test_02_check_versions_and_uses_latest(self):
        for tag in ('v0.1.1', 'v0.1.0'):
            with self.subTest(tag=tag):
                assets = []
                for name in ('networklab-%s.zip' % tag, 'networklab-%s.zip.sha256' % tag):
                    assets.append({'name':name, 'browser_download_url':'https://github.com/example/NetworkLab/releases/download/%s/%s' % (tag, name)})
                with mock.patch.object(updater,'release_metadata',return_value={'tag_name':tag, 'assets':assets}):
                    self.assertEqual(self.run_main('check'),0)

    def test_03_dry_run_does_not_network_or_modify(self):
        with mock.patch.object(updater, 'release_metadata', side_effect=AssertionError('went online')):
            self.assertEqual(self.run_main(dry_run=True), 0)
        self.verify_untouched()

    def test_04_real_lifecycle_success_with_wrapped_archive(self):
        r, d = self.remote(archive(wrapping=True))
        with r, d:
            self.assertEqual(self.run_main(), 0)
        self.assertEqual(updater.app_version(self.app), 'v0.1.1')
        self.assertEqual(self.saved.read_bytes(), b'keep reports')
        self.assertEqual(self.saved_config, (self.home/'config/c.conf').read_bytes())
        self.assertEqual(list(self.home.glob('.netlab-upgrade-*')), [])
        self.assertEqual(self.run_cli('self-test', '--quiet').returncode, 0)

    def test_05_sha_mismatch_fails_closed(self):
        r,d = self.remote(checksum='0'*64)
        with r,d:
            self.assertEqual(self.run_main(), 9)
        self.verify_untouched()

    def test_06_wrong_code_version_rejected(self):
        r,d = self.remote(archive(version='v0.1.2'))
        with r,d:
            self.assertEqual(self.run_main(), 9)
        self.verify_untouched()

    def test_07_broken_new_version_no_swap(self):
        r,d = self.remote(archive(broken=True))
        with r,d:
            self.assertEqual(self.run_main(), 5)
        self.verify_untouched()

    def test_08_post_cutover_failure_rolls_back(self):
        original = updater.check_new_app
        calls = [0]
        def flaky(stage, home):
            calls[0] += 1
            if calls[0] == 2:
                raise updater.UpdateError('injected post-swap failure')
            return original(stage,home)
        r,d = self.remote()
        with r,d,mock.patch.object(updater, 'check_new_app', side_effect=flaky):
            self.assertEqual(self.run_main(), 5)
        self.assertEqual(calls[0], 2)
        self.verify_untouched()
        self.assertEqual(list(self.home.glob('.netlab-upgrade-*')), [])

    def test_09_bad_archive_paths(self):
        for path in ('../evil', '/tmp/evil', 'lib\\bad.sh'):
            with self.subTest(path=path):
                bio = io.BytesIO()
                with zipfile.ZipFile(bio, 'w') as z: z.writestr(path, b'hi')
                stage = self.path/'extract'
                stage.mkdir(exist_ok=True)
                with self.assertRaises(updater.UpdateError):
                    updater.unpack_verified_archive(bio.getvalue(), stage)
                shutil.rmtree(stage)

    def test_10_reject_zip_symlink_duplicate(self):
        bio = io.BytesIO()
        with zipfile.ZipFile(bio,'w') as z:
            sym = zipfile.ZipInfo('lib/link.sh'); sym.create_system = 3
            sym.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(sym,'../../etc')
        with self.assertRaises(updater.UpdateError):
            updater.unpack_verified_archive(bio.getvalue(), self.path/'sym')
        bio = io.BytesIO()
        with zipfile.ZipFile(bio,'w') as z:
            z.writestr('lib/Foo.sh','one'); z.writestr('lib/foo.sh','two')
        with self.assertRaises(updater.UpdateError):
            updater.unpack_verified_archive(bio.getvalue(), self.path/'dup')

    def test_11_release_asset_urls_are_bound(self):
        good = {'assets':[{'name':'networklab-v0.1.1.zip', 'browser_download_url':'https://evil.example/thing'},
                          {'name':'networklab-v0.1.1.zip.sha256', 'browser_download_url':'https://github.com/example/NetworkLab/releases/download/v0.1.1/networklab-v0.1.1.zip.sha256'}]}
        with self.assertRaises(updater.UpdateError):
            updater.release_asset_urls('example/NetworkLab', good,'v0.1.1')

    def test_12_lock_contention(self):
        import fcntl
        with open(self.home/'.install.lock','a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.run_main(), 10)
        self.verify_untouched()

    def test_13_invalid_config_and_symlink(self):
        path = self.home/'config/update-source.json'
        for value in ('{"github_repo":"../../bad"}', '{"github_repo":"example/NetworkLab","foo":1}', '{"github_repo":"x/y","github_repo":"a/b"}'):
            with self.subTest(value=value):
                path.write_text(value)
                self.assertEqual(self.run_main('check'), 3)
        path.unlink()
        path.symlink_to(self.home/'config/c.conf')
        self.assertEqual(self.run_main('check'), 9)

    def test_14_downgrade_rejected_and_same_no_network(self):
        self.assertEqual(self.run_main(tag='v0.0.9'), 3)
        self.assertEqual(self.run_main(tag='v0.1.0'), 0)
        self.verify_untouched()

    def test_15_noninstalled_does_not_create_home(self):
        shutil.rmtree(self.home/'app')
        self.assertEqual(self.run_main(), 3)
        self.assertFalse((self.home/'app').exists())

    def test_17_two_role_update_preserves_server_identity(self):
        p = subprocess.run(['sh', str(ROOT/'install.sh'), '--role', 's', '--skip-self-test'], env=self.env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=40)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        old_server = (self.home/'config/s.conf').read_bytes()
        r, d = self.remote()
        with r, d:
            self.assertEqual(self.run_main(), 0)
        self.assertEqual((self.home/'config/s.conf').read_bytes(), old_server)
        self.assertEqual(self.run_cli('self-test', '--quiet', role='s').returncode, 0)

    def test_18_untrusted_redirect_rejected(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def geturl(self): return 'http://evil.example/binary.zip'
            def read(self, n): return b'invalid'
        with mock.patch.object(updater, 'urlopen', return_value=FakeResponse()):
            with self.assertRaises(updater.UpdateError) as cm:
                updater.url_bytes('https://github.com/example/NetworkLab/releases/download/v0.1.1/b.zip', 100)
        self.assertEqual(cm.exception.code, 9)

    def test_19_config_directory_symlink_rejected(self):
        config = self.home/'config'
        elsewhere = self.home/'backup-config'
        config.rename(elsewhere)
        config.symlink_to(elsewhere, target_is_directory=True)
        self.assertEqual(self.run_main('check'), 9)

    def test_16_invalid_sidecar_and_tag(self):
        self.assertRaises(updater.UpdateError, updater.get_expected_digest,b'sha-not-digest','xx.zip')
        self.assertRaises(updater.UpdateError, updater.get_expected_digest,(b'a'*64)+b'  bad.zip','xx.zip')
        with mock.patch.object(updater,'url_bytes',return_value=b'{"tag_name":"v0.1.2"}'):
            with self.assertRaises(updater.UpdateError):
                updater.release_metadata('example/NetworkLab','v0.1.1')


if __name__ == '__main__':
    unittest.main(verbosity=2)
