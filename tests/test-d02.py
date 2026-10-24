#!/usr/bin/env python3
"""D02 Mac local inventory fixture & real-host checks. Never probes Internet."""
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
from c_inventory import (collect_snapshot, make_handoff, parse_proxy, parse_dns,
                         parse_route, parse_interfaces, hardware_ports, _write_json_new)

SAMPLES = {
 'ifconfig': '''lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
\tinet6 ::1 prefixlen 128
\ten0: not a valid header
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tether aa:bb:cc:dd:ee:ff
\tinet6 fe80::abcd%en0 prefixlen 64 secured scopeid 0x8
\tinet 172.20.10.2 netmask 0xffffff00 broadcast 172.20.10.255
\tstatus: active
utun4: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380
\tinet6 fe80::1%utun4 prefixlen 64
\tstatus: active
''',
 'networksetup': '''Hardware Port: Wi-Fi
Device: en0
Ethernet Address: aa:bb:cc:dd:ee:ff

Hardware Port: iPhone USB
Device: en9
Ethernet Address: ff:bb:cc:dd:ee:aa
''',
 'route4': '   route to: default\ndestination: default\ngateway: 172.20.10.1\ninterface: en0\n',
 'route6': '   route to: default\ndestination: default\ninterface: utun4\n',
 'dns': '''DNS configuration
resolver #1
  nameserver[0] : 192.168.1.1
  search domain[0] : private-work.example
  if_index : 8 (en0)
resolver #2
  domain : confidential.internal
  nameserver[0] : 1.1.1.1
''',
 'proxy': '''<dictionary> {
  HTTPEnable : 0
  HTTPProxy : private.proxy.example
  HTTPSEnable : 0
  SOCKSEnable : 1
  SOCKSProxy : private.internal
  ProxyAutoConfigEnable : 0
  ProxyAutoConfigURLString : https://token-sensitive.example/secret
}
''',
 'sw_vers': '27.0.1\n'
}


class D02Tests(unittest.TestCase):
    def test_native_snapshot_and_privacy(self):
        snap = collect_snapshot(lambda key: SAMPLES[key], system='Darwin')
        self.assertEqual(snap['os']['version'], '27.0.1')
        self.assertEqual(snap['network']['default_routes']['ipv4']['interface'], 'en0')
        self.assertEqual(snap['network']['connection']['kind_hint'], 'wifi')
        self.assertEqual(snap['network']['connection']['hotspot_hint'], 'iphone_tether_subnet_possible')
        self.assertFalse(snap['network']['connection']['hotspot_confirmed'])
        self.assertEqual(snap['tunnel']['utun_interfaces_observed'], ['utun4'])
        self.assertFalse(snap['tunnel']['ipv4_default_uses_utun'])
        self.assertTrue(snap['tunnel']['ipv6_default_uses_utun'])
        self.assertTrue(snap['proxy']['enabled'])
        self.assertEqual(snap['dns']['resolvers'][1]['nameservers'], ['1.1.1.1'])
        serialized = json.dumps(snap)
        for secret in ('aa:bb:cc', 'private-work.example', 'confidential.internal',
                       'private.proxy.example', 'token-sensitive.example'):
            self.assertNotIn(secret, serialized)
        self.assertIsNone(snap['public_network']['isp'])
        self.assertFalse(snap['public_network']['external_probe_performed'])

    def test_connection_heuristics_and_unknowns(self):
        data = dict(SAMPLES, route4='interface: en9\n', dns=None, proxy=None, route6=None)
        snap = collect_snapshot(lambda key: data[key], system='Darwin')
        # en9 is listed as a configured hardware port, but has no live ifconfig state.
        self.assertEqual(snap['network']['connection']['kind_hint'], 'unknown')
        self.assertIsNone(snap['proxy']['enabled'])
        self.assertFalse(snap['dns']['available'])
        self.assertIsNone(snap['tunnel']['ipv6_default_uses_utun'])
        self.assertIsNone(snap['network']['default_routes']['ipv6']['gateway'])
        data['ifconfig'] += 'en9: flags=8863<UP,RUNNING> mtu 1500\n\tstatus: active\n'
        self.assertEqual(collect_snapshot(lambda key: data[key], system='Darwin')['network']['connection']['kind_hint'],
                         'iphone_usb_likely')
        data['route4'] = 'interface: utun4\n'
        self.assertEqual(collect_snapshot(lambda key: data[key], system='Darwin')['network']['connection']['kind_hint'],
                         'tunnel_default_route')

    def test_missing_critical_and_non_macos(self):
        with self.assertRaisesRegex(RuntimeError, 'requires macOS'):
            collect_snapshot(lambda key: SAMPLES[key], system='Linux')
        with self.assertRaisesRegex(RuntimeError, 'ifconfig'):
            collect_snapshot(lambda key: None if key == 'ifconfig' else SAMPLES[key], system='Darwin')
        with self.assertRaisesRegex(RuntimeError, 'no parseable interfaces'):
            parse_interfaces('', {})
        with self.assertRaisesRegex(RuntimeError, 'interface count exceeds'):
            parse_interfaces(''.join('en%d: flags=1<UP> mtu 1500\n' % i for i in range(130)), {})

    def test_output_exclusive_and_contract(self):
        snap = collect_snapshot(lambda key: SAMPLES[key], system='Darwin')
        handoff = make_handoff(snap)
        self.assertFalse(handoff['synthetic'])
        self.assertEqual(handoff['requested_tests'], ['c-local-environment'])
        self.assertEqual(handoff['tests'][0]['evidence_scope'], 'local')
        self.assertEqual(handoff['tests'][0]['data_provenance'], 'observed')
        self.assertEqual(handoff['tests'][0]['status'], 'completed')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'raw.json'
            _write_json_new(path, snap)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                _write_json_new(path, {})
            with self.assertRaisesRegex(RuntimeError, 'safety bound'):
                _write_json_new(Path(temp) / 'too-large.json', {'data': 'a' * 300000})

    def test_guard_no_context(self):
        env = dict(os.environ, NETLAB_INTERNAL_WORKER='1', PYTHONDONTWRITEBYTECODE='1')
        env.pop('NETLAB_WORK_DIR', None)
        env.pop('NETLAB_CONTEXT_FILE', None)
        p = subprocess.run(['bash', str(ROOT / 'c/c-inventory.sh')], env=env,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=12)
        self.assertEqual(p.returncode, 9, p.stderr)
        self.assertIn('SAFETY_BLOCKED', p.stderr)

    @unittest.skipUnless(platform.system() == 'Darwin', 'Real macOS-only integration')
    def test_full_cli_report_writer_macos(self):
        import report
        with tempfile.TemporaryDirectory(prefix='netlab-d02-') as temp:
            home = Path(temp) / 'home'
            (home / 'config').mkdir(parents=True)
            (home / 'config/c.conf').write_text('[general]\nconfig_version=1\ndefault_profile=quick\n'
                                                   '[paths]\ntargets_file=targets.conf\n')
            env = dict(os.environ, NETLAB_HOME=str(home), PYTHONDONTWRITEBYTECODE='1')
            argv = ['bash', str(ROOT / 'netlab-c.sh'), 'inventory', '--non-interactive']
            pre = subprocess.run(argv + ['--dry-run'], env=env, capture_output=True,
                                 text=True, timeout=15)
            self.assertEqual(pre.returncode, 8, pre.stderr)
            self.assertFalse((home / 'results').exists())
            p = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=50)
            self.assertEqual(p.returncode, 0, p.stderr)
            manifests = list((home / 'results').rglob('*-manifest-*.json'))
            self.assertEqual(len(manifests), 1, p.stdout)
            manifest = report.verify_manifest(manifests[0])
            self.assertEqual(manifest['role'], 'C')
            self.assertEqual(manifest['module_id'], 'c-inventory')
            self.assertEqual(manifest['status'], 'completed')
            self.assertFalse(manifest['synthetic'])
            summary = next((home / 'results').rglob('*-summary-*.json'))
            item = json.loads(summary.read_text())['tests'][0]
            self.assertEqual(item['test_id'], 'c-local-environment')
            self.assertEqual(item['status'], 'completed')
            raw = next((home / 'results').rglob('*-c-local-environment-*.json'))
            obj = json.loads(raw.read_text())
            self.assertEqual(obj['source'], 'local-macos-readonly')
            self.assertFalse(obj['public_network']['external_probe_performed'])
            self.assertTrue(obj['network']['interfaces'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
