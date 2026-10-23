#!/usr/bin/env python3
"""D01 offline source/worker/real-Linux inventory contract tests.

All integration tests have zero outbound network activity; no public services,
SSH, iperf3 or privileged operations. Real system reads occur only in Linux CI.
"""
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from s_inventory import collect_snapshot, make_handoff, _write_json_new  # noqa: E402
import report  # noqa: E402


class D01Tests(unittest.TestCase):
    def fixture(self, path):
        proc = path / 'proc'
        sysroot = path / 'sys'
        etc = path / 'etc'
        (sysroot / 'class/net/eth0').mkdir(parents=True)
        (proc / 'sys/net/ipv4').mkdir(parents=True)
        (proc / 'sys/net/core').mkdir(parents=True)
        (proc / 'net').mkdir(parents=True)
        (proc / '101').mkdir()
        etc.mkdir()
        (etc / 'os-release').write_text('ID=alpine\nVERSION_ID="3.21"\n')
        (sysroot / 'class/net/eth0/operstate').write_text('up\n')
        (sysroot / 'class/net/eth0/mtu').write_text('1500\n')
        (sysroot / 'class/net/eth0/speed').write_text('1000\n')
        (proc / 'sys/net/ipv4/tcp_congestion_control').write_text('bbr\n')
        (proc / 'sys/net/core/default_qdisc').write_text('fq\n')
        (proc / 'net/if_inet6').write_text('20010db8000000000000000000000001 02 40 00 80 eth0\n')
        (proc / '101/comm').write_text('xray\n')
        (proc / 'cpuinfo').write_text('model name\t: Fixture CPU\n')
        return proc, sysroot, etc

    def test_linux_fixture_snapshot_and_b09_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            proc, sysroot, etc = self.fixture(Path(temp))
            before = sorted(str(p) for p in Path(temp).rglob('*'))
            snapshot = collect_snapshot(proc, sysroot, etc, ipv4_lookup=lambda name: '192.0.2.10',
                                        system={'system': 'Linux', 'kernel': '6.1.0',
                                                'architecture': 'x86_64', 'cpu_count': 2})
            self.assertEqual(snapshot['tcp']['congestion_control'], 'bbr')
            self.assertEqual(snapshot['network']['ipv4_interface_count'], 1)
            self.assertEqual(snapshot['network']['ipv6_address_count'], 1)
            self.assertEqual(snapshot['process_observation']['visible_process_counts']['xray'], 1)
            self.assertEqual(snapshot['os']['cpu_logical'], 2)
            self.assertEqual(snapshot['network']['interfaces'][0]['link_speed_mbps_reported'], 1000)
            self.assertTrue(snapshot['limits']['no_active_network_probe'])
            handoff = make_handoff(snapshot)
            clean = report.validate_handoff(handoff)
            self.assertFalse(clean['synthetic'])
            self.assertEqual(clean['tests'][0]['data_provenance'], 'observed')
            self.assertEqual(clean['tests'][0]['network']['direction'], 'LOCAL')
            self.assertEqual(clean['requested_tests'], ['s-static'])
            self.assertEqual(before, sorted(str(p) for p in Path(temp).rglob('*')))

    def test_missing_optional_tuning_is_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            proc, sysroot, etc = self.fixture(Path(temp))
            (proc / 'sys/net/core/default_qdisc').unlink()
            snapshot = collect_snapshot(proc, sysroot, etc, ipv4_lookup=lambda _: None,
                                        system={'system': 'Linux', 'kernel': 'x',
                                                'architecture': 'arm64', 'cpu_count': None})
            self.assertIsNone(snapshot['tcp']['default_qdisc'])
            self.assertEqual(snapshot['network']['ipv4_interface_count'], 0)
            self.assertIsNone(snapshot['os']['cpu_logical'])

    def test_reject_missing_sysfs_and_non_linux(self):
        with tempfile.TemporaryDirectory() as temp:
            proc, sysroot, etc = self.fixture(Path(temp))
            with self.assertRaisesRegex(RuntimeError, 'requires Linux'):
                collect_snapshot(proc, sysroot, etc, system={'system': 'Darwin'})
            with self.assertRaisesRegex(RuntimeError, 'sys/class/net unavailable'):
                collect_snapshot(proc, Path(temp) / 'other', etc,
                                 system={'system': 'Linux', 'kernel': 'x',
                                         'architecture': 'x', 'cpu_count': 1})

    def test_exclusive_output_and_size_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            f = Path(temp) / 'small.json'
            _write_json_new(f, {'actual': True})
            self.assertEqual(json.loads(f.read_text()), {'actual': True})
            self.assertEqual(f.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                _write_json_new(f, {'overwrite': True})
            with self.assertRaisesRegex(RuntimeError, 'safety bound'):
                _write_json_new(Path(temp) / 'large.json', {'data': 'x' * 300000})

    def test_internal_entry_without_context_blocks(self):
        env = dict(os.environ, NETLAB_INTERNAL_WORKER='1')
        for key in ('NETLAB_WORK_DIR', 'NETLAB_CONTEXT_FILE'):
            env.pop(key, None)
        p = subprocess.run(['bash', str(ROOT / 's/s-inventory.sh')], env=env,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10)
        self.assertEqual(p.returncode, 9, p.stderr)
        self.assertIn('SAFETY_BLOCKED', p.stderr)

    @unittest.skipUnless(platform.system() == 'Linux', 'Real S inventory only runs on Linux')
    def test_full_cli_report_writer_offline_linux(self):
        with tempfile.TemporaryDirectory(prefix='netlab-d01-') as temp:
            home = Path(temp) / 'home'
            (home / 'config').mkdir(parents=True)
            (home / 'config/s.conf').write_text('[general]\nconfig_version=1\nserver_id=lab-vps\n'
                                                 'timezone=UTC+08:00\ndefault_profile=quick\n')
            env = dict(os.environ, NETLAB_HOME=str(home), PYTHONDONTWRITEBYTECODE='1')
            base = ['bash', str(ROOT / 'netlab-s.sh'), 'inventory', '--non-interactive']
            preview = subprocess.run(base + ['--dry-run'], env=env, capture_output=True, text=True,
                                     stdin=subprocess.DEVNULL, timeout=12)
            self.assertEqual(preview.returncode, 8, preview.stderr)
            self.assertFalse((home / 'results').exists())
            p = subprocess.run(base, env=env, capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, timeout=20)
            self.assertEqual(p.returncode, 0, p.stderr)
            reports = list((home / 'results').rglob('*-manifest-*.json'))
            self.assertEqual(len(reports), 1, p.stdout)
            manifest = report.verify_manifest(reports[0])
            self.assertEqual(manifest['module_id'], 's-inventory')
            self.assertEqual(manifest['scope_id'], 'lab-vps')
            self.assertEqual(manifest['status'], 'completed')
            self.assertFalse(manifest['synthetic'])
            self.assertEqual(manifest['networklab_version'], '0.1.1')
            summary = next((home / 'results').rglob('*-summary-*.json'))
            record = json.loads(summary.read_text())
            self.assertEqual(record['tests'][0]['test_id'], 's-static')
            self.assertFalse(record['synthetic'])
            self.assertEqual(record['tests'][0]['status'], 'completed')
            self.assertIn('s-static', record['tests'][0]['raw_files'][0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
