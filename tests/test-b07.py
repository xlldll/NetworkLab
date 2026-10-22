#!/usr/bin/env python3
"""B07 isolated C config-management tests, no network or editor side effects."""
import importlib.util
import os
import pty
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('config_manager', ROOT/'lib'/'config_manager.py')
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

CFG = '''[general]\nconfig_version = 1\ndefault_profile = quick\n[network]\npreferred_ip_family = auto\n[proxy]\nprotocol = http\nhost = 127.0.0.1\nport = 7890\n[paths]\ntargets_file = targets.conf\n'''
ROW = '東京 AWS|aws-tokyo|direct|203.0.113.10|2001:db8::12|5202|443|aws-tokyo\n'
ADD = ('targets','add','--name','美西 NAT','--id','nat-us','--type','nat','--ipv4','198.51.100.12','--iperf-port','48801','--mtr-port','443','--non-interactive')

class B07Tests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix='netlab-b07-')
        self.home = Path(self.dir.name)/'home'
        self.conf = self.home/'config'
        self.conf.mkdir(parents=True, mode=0o700)
        self.config_file = self.conf/'c.conf'
        self.target_file = self.conf/'targets.conf'
        self.config_file.write_text(CFG,encoding='utf-8')
        self.target_file.write_text('# header\n'+ROW,encoding='utf-8')
        self.env = dict(os.environ, NETLAB_HOME=str(self.home))

    def tearDown(self):
        self.dir.cleanup()

    def cli(self,*args):
        return subprocess.run(['bash',str(ROOT/'netlab-c.sh'),*args],env=self.env,
                              stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=6)

    def test_list_show_and_validate(self):
        for args in (('targets','list'),('targets','show','aws-tokyo'),('targets','validate')):
            with self.subTest(args=args):
                p=self.cli(*args)
                self.assertEqual(p.returncode,0,p.stderr)
                self.assertIn('aws-tokyo', p.stdout if args[1]!='validate' else self.target_file.read_text())
        self.assertEqual(self.cli('targets','show','not-exist').returncode,3)

    def test_add_atomic_and_duplicate(self):
        p=self.cli(*ADD)
        self.assertEqual(p.returncode,0,p.stderr)
        text=self.target_file.read_text()
        self.assertIn('# header',text)
        self.assertIn('美西 NAT|nat-us|nat|198.51.100.12||48801|443|\n',text)
        self.assertEqual(self.cli(*ADD).returncode,3)
        self.assertEqual(self.target_file.read_text(),text)
        self.assertEqual(len(list(self.conf.glob('.targets.conf.backup-*'))),1)

    def test_dry_run_side_effect_free(self):
        previous=self.target_file.read_bytes()
        p=self.cli(*ADD,'--dry-run')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('DRY_RUN',p.stdout)
        self.assertEqual(previous,self.target_file.read_bytes())
        self.assertFalse(list(self.conf.glob('.targets.conf.lock')))
        self.assertFalse(list(self.conf.glob('.targets.conf.backup-*')))
        p=self.cli('targets','edit','--editor','nano','--dry-run')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(previous,self.target_file.read_bytes())

    def test_bad_config_is_rejected(self):
        original=self.target_file.read_bytes()
        for bad in ('[general]\nconfig_version=2\n', '[general]\nconfig_version=1\nx=1\n',
                    '[general]\nconfig_version=1\nconfig_version=1\n',
                    '[general]\nconfig_version=1\n[paths]\ntargets_file=\n',
                    '[general]\nconfig_version=1\n[proxy]\nhost=example.com\n'):
            with self.subTest(bad=bad):
                self.config_file.write_text(bad)
                p=self.cli('config','validate')
                self.assertEqual(p.returncode,3,(p.stdout,p.stderr))
        self.assertEqual(original,self.target_file.read_bytes())

    def test_validation_error_details_and_malformed_fields(self):
        badrows = [
            ROW + ROW,
            'Bad|bad|direct|999.999.999.999||5202|443|\n',
            'Bad|bad|nat|198.51.100.1||0|443|\n',
            'Bad|bad|nat|198.51.100.1||5202|443\n',
            'Bad|bad|nat|||5202|443|\n',
            'Bad|bad|nat|198.51.100.1||5202|443|evil ssh\n',
            'Bad|bad|nat|198.51.100.1||5202|443|\nBad|bad|nat|198.51.100.2||5202|443|\n',
        ]
        for text in badrows:
            with self.subTest(text=text[:40]):
                self.target_file.write_text(text)
                p=self.cli('targets','validate')
                self.assertEqual(p.returncode,3,p.stderr)
                self.assertIn('line',p.stderr)

    def test_invalid_add_keeps_source(self):
        source=self.target_file.read_text()
        cases=[('--ipv4','999.888.10.1'),('--iperf-port','70000'),('--name','abc|def')]
        for key,value in cases:
            args=list(ADD)
            pos=args.index(key)
            args[pos+1]=value
            result=self.cli(*args)
            self.assertIn(result.returncode,(2,3),result.stderr)
            self.assertEqual(self.target_file.read_text(),source)

    def test_write_atomic_failure_and_backup(self):
        src=self.target_file.read_text()
        with cm.locked(self.target_file):
            with self.assertRaises(cm.ConfigurationError):
                cm.atomic_commit(self.target_file,src+'Bad|bad|nat|999.2.3.4||5202|443|\n')
        self.assertEqual(self.target_file.read_text(),src)
        with cm.locked(self.target_file):
            cm.atomic_commit(self.target_file,src+'New|new|nat|198.51.100.2||5202|443|\n')
        self.assertIn('New|new|nat',self.target_file.read_text())
        self.assertEqual(self.target_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(list(self.conf.glob('.targets.conf.backup-*'))),1)

    def test_symlink_protection(self):
        real = self.conf/'real.txt'
        real.write_text(ROW)
        self.target_file.unlink()
        self.target_file.symlink_to(real)
        p=self.cli('targets','validate')
        self.assertEqual(p.returncode,9,p.stderr)
        p=self.cli(*ADD)
        self.assertEqual(p.returncode,9,p.stderr)
        self.assertEqual(real.read_text(),ROW)

    def test_c_config_validate_and_override(self):
        self.assertEqual(self.cli('config','validate').returncode,0)
        alt = self.conf/'extra.ini'
        alt.write_text(CFG.replace('targets.conf','alt_targets.conf'))
        (self.conf/'alt_targets.conf').write_text('Other|other|nat|192.0.2.10||5202|443|\n')
        p=self.cli('targets','list','--config',str(alt))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('other',p.stdout)
        self.assertNotIn('aws-tokyo',p.stdout)

    def test_edit_requires_tty_or_safe_dry_run(self):
        before=self.target_file.read_text()
        p=self.cli('targets','edit','--editor','nano')
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertEqual(before,self.target_file.read_text())
        p=self.cli('targets','edit','--editor','nano','--dry-run')
        self.assertEqual(p.returncode,0,p.stderr)

    def test_tty_editor_candidate_commit_or_rollback(self):
        # Emulate nano with a script. It edits only the provided candidate file.
        # Both stdio streams are connected to a PTY, without a human/editor UI.
        bin_dir = Path(self.dir.name)/'bin'
        bin_dir.mkdir()
        fake_nano = bin_dir/'nano'
        env = dict(self.env, PATH=str(bin_dir)+os.pathsep+self.env.get('PATH',''))
        before = self.target_file.read_bytes()
        master, slave = pty.openpty()
        try:
            fake_nano.write_text('#!/bin/sh\nprintf "Invalid|oops|nat|INVALID||5202|443|\\n" >> "$1"\n')
            fake_nano.chmod(0o755)
            p=subprocess.run(['bash',str(ROOT/'netlab-c.sh'),'targets','edit','--editor','nano'],
                             stdin=slave,stdout=slave,stderr=slave,env=env,timeout=6)
            self.assertEqual(p.returncode,3)
            self.assertEqual(self.target_file.read_bytes(),before)
            self.assertFalse(list(self.conf.glob('.targets.conf.backup-*')))
            fake_nano.write_text('#!/bin/sh\nprintf "New|new|nat|198.51.100.2||5202|443|\\n" >> "$1"\n')
            p=subprocess.run(['bash',str(ROOT/'netlab-c.sh'),'targets','edit','--editor','nano'],
                             stdin=slave,stdout=slave,stderr=slave,env=env,timeout=6)
            self.assertEqual(p.returncode,0)
            self.assertIn('New|new|nat|198.51.100.2',self.target_file.read_text())
            backups=list(self.conf.glob('.targets.conf.backup-*'))
            self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].read_bytes(),before)
        finally:
            os.close(slave)
            os.close(master)

    def test_runner_remains_not_implemented_for_tests(self):
        p=self.cli('inventory','--non-interactive')
        self.assertEqual(p.returncode,8,p.stderr)
        self.assertFalse((self.home/'results').exists())

if __name__=='__main__':
    unittest.main(verbosity=2)
