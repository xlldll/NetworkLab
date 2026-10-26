#!/usr/bin/env python3
"""D03 offline fixtures + Mac loopback CLI → B09 integration, no Internet."""
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from c_tcp_connect import (validate_endpoint, execute, handoff, percentile,
                           _write_json_new, PROFILES)


class D03Tests(unittest.TestCase):
    def test_reject_unsafe_and_ambiguous_addresses(self):
        for host in ('example.org', '', '0.0.0.0', '224.0.0.1',
                     'fe80::1', '192.168.1.1', '2001:db8::1', '1.1.1.1%en0'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                validate_endpoint(host, 443)
        for p in (0, 65536, '443', None):
            with self.subTest(port=p), self.assertRaises(ValueError):
                validate_endpoint('1.1.1.1', p)
        self.assertEqual(validate_endpoint('1.1.1.1', 443), ('1.1.1.1', 443, 4))
        self.assertEqual(validate_endpoint('2606:4700:4700::1111', 443)[2], 6)

    def test_percentiles_and_no_success(self):
        self.assertIsNone(percentile([], 95))
        self.assertEqual(percentile([10], 99), 10)
        self.assertEqual(percentile([10, 20, 30], 50), 20)
        self.assertEqual(percentile([10, 20, 30], 95), 29)

    def test_partial_failed_and_metrics(self):
        for successful in (0, 4, 12):
            seen = []
            def connector(_ip, _port, family, _timeout):
                seen.append(family)
                return (10.0 + len(seen), None if len(seen) <= successful else 'timeout')
            raw, stats = execute('127.0.0.1', 443, 'quick', connector=connector,
                                 sleeper=lambda _: None,
                                 route_reader=lambda *_: {'interface': 'lo0', 'available': True},
                                 proxy_reader=lambda: True)
            record, status = handoff(raw, stats)
            self.assertEqual(status, 'completed' if successful == 12 else ('partial' if successful else 'failed'))
            self.assertEqual(len(raw['attempts']), PROFILES['quick'])
            self.assertEqual(stats['sample_count'], 12)
            self.assertEqual(stats['successful_samples'], successful)
            self.assertEqual(stats['success_pct'], successful / 12 * 100 if successful in (0,12) else round(successful / 12 * 100, 3))
            self.assertEqual(raw['route_and_proxy_hints']['effective_network_path_verified_direct'], False)
            self.assertEqual(record['tests'][0]['network']['proxy_mode'], 'unknown')
            self.assertEqual(record['tests'][0]['evidence_scope'], 'local')
            self.assertEqual(seen, [4] * 12)
            self.assertTrue(any(x['code'] == 'PATH_UNVERIFIED' for x in record['tests'][0]['warnings']))
            if successful == 0:
                self.assertIsNone(stats['tcp_connect_p95_ms'])
            if successful == 12:
                self.assertGreater(stats['p95_minus_p50_ms'], 0)

    def test_ipv6_and_no_dns(self):
        calls = []
        def connector(ip, port, family, timeout):
            calls.append((ip, port, family, timeout))
            return (1.0, None)
        raw, stats = execute('2606:4700:4700::1111', 443, 'quick', connector=connector,
                             sleeper=lambda _: None,
                             route_reader=lambda *_: {'interface': None, 'available': False},
                             proxy_reader=lambda: None)
        self.assertEqual(len(calls), 12)
        self.assertTrue(all(c[2] == 6 and c[0] == '2606:4700:4700::1111' for c in calls))
        self.assertEqual(handoff(raw, stats)[0]['tests'][0]['network']['ip_family'], 6)
        self.assertEqual(handoff(raw, stats)[0]['tests'][0]['evidence_scope'], 'public_path')

    def test_exclusive_output(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'raw.json'
            _write_json_new(p, {'some': 'evidence'})
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                _write_json_new(p, {'overwritten': True})
            with self.assertRaises(RuntimeError):
                _write_json_new(Path(temp) / 'big.json', {'blob': 'X' * 270000})

    def test_unauthorized_internal_worker(self):
        env = dict(os.environ, NETLAB_INTERNAL_WORKER='1')
        env.pop('NETLAB_WORK_DIR', None)
        env.pop('NETLAB_CONTEXT_FILE', None)
        p = subprocess.run(['bash', str(ROOT / 'c/c-standalone.sh')], env=env,
                           capture_output=True, text=True, timeout=12)
        self.assertEqual(p.returncode, 9, p.stderr)
        self.assertIn('SAFETY_BLOCKED', p.stderr)

    def test_cli_requires_explicit_ip_port(self):
        with tempfile.TemporaryDirectory() as t:
            env = dict(os.environ, NETLAB_HOME=t)
            cli = ['bash', str(ROOT / 'netlab-c.sh'), 'standalone']
            for suffix in ([], ['--tcp-ip', '1.1.1.1'],
                           ['--tcp-port', '443'],
                           ['--tcp-ip', 'example.com', '--tcp-port', '443'],
                           ['--tcp-ip', '192.168.1.1', '--tcp-port', '443']):
                p = subprocess.run(cli + suffix + ['--non-interactive'], env=env,
                                   capture_output=True, text=True, timeout=12)
                self.assertEqual(p.returncode, 2, p.stderr)
            self.assertFalse((Path(t) / 'results').exists())
            p = subprocess.run(cli + ['--tcp-ip','127.0.0.1','--tcp-port','1','--dry-run'],
                               env=env, capture_output=True, text=True, timeout=12)
            self.assertEqual(p.returncode, 8, p.stderr)
            self.assertFalse((Path(t) / 'results').exists())

    @unittest.skipUnless(platform.system() == 'Darwin', 'Mac-only loopback CLI acceptance')
    def test_real_mac_loopback_and_report(self):
        import report
        with tempfile.TemporaryDirectory(prefix='netlab-d03-') as t:
            home = Path(t) / 'home'
            (home / 'config').mkdir(parents=True)
            (home / 'config/c.conf').write_text('[general]\nconfig_version=1\ndefault_profile=quick\n')
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', 0))
            listener.listen(32)
            listener.settimeout(0.2)
            stop = threading.Event()
            def accept_loop():
                while not stop.is_set():
                    try:
                        sock, _ = listener.accept()
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    sock.close()
            worker = threading.Thread(target=accept_loop, daemon=True)
            worker.start()
            try:
                port = listener.getsockname()[1]
                env = dict(os.environ, NETLAB_HOME=str(home), PYTHONDONTWRITEBYTECODE='1')
                argv = ['bash', str(ROOT / 'netlab-c.sh'), 'standalone', '--profile', 'quick',
                        '--tcp-ip', '127.0.0.1', '--tcp-port', str(port), '--non-interactive']
                p = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL,
                                   capture_output=True, text=True, timeout=45)
                self.assertEqual(p.returncode, 0, p.stderr)
                manifests = list((home / 'results').rglob('*-manifest-*.json'))
                self.assertEqual(len(manifests), 1, p.stdout)
                m = report.verify_manifest(manifests[0])
                self.assertEqual(m['module_id'], 'c-standalone')
                self.assertFalse(m['synthetic'])
                summary = list((home / 'results').rglob('*-summary-*.json'))
                self.assertEqual(len(summary), 1)
                item = json.loads(summary[0].read_text())['tests'][0]
                self.assertEqual(item['status'], 'completed')
                self.assertEqual(item['metrics']['sample_count'], 12)
                self.assertEqual(item['metrics']['successful_samples'], 12)
                self.assertEqual(item['network']['proxy_mode'], 'unknown')
                raws = [e for e in m['files'] if e['kind'] == 'raw']
                self.assertEqual(len(raws), 1)
                raw = json.loads((manifests[0].parent / raws[0]['path']).read_text())
                self.assertEqual(len(raw['attempts']), 12)
                self.assertTrue(all(a['success'] for a in raw['attempts']))
            finally:
                stop.set()
                listener.close()
                worker.join(timeout=2)

if __name__ == '__main__':
    unittest.main(verbosity=2)
