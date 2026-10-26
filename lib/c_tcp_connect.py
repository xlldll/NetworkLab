#!/usr/bin/env python3
"""D03: explicit IPv4/IPv6 numeric TCP connect samples, no application bytes.

Python's system socket API performs the TCP handshake; NetworkLab only times,
classifies and publishes evidence. No DNS, HTTP, proxy configuration or changes.
"""
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import re
import socket
import statistics
import subprocess
import sys
import time

from module_entry import InvalidContext, validate_context

PROFILES = {'quick': 12, 'standard': 30, 'deep': 100}
TIMEOUT_SEC = 1.0
INTERVAL_SEC = 0.05
MAX_JSON = 256 * 1024


def validate_endpoint(address, port):
    if not isinstance(address, str) or len(address) > 64 or '%' in address:
        raise ValueError('destination must be a numeric IPv4/IPv6 address without scope')
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        raise ValueError('destination must be a numeric IPv4/IPv6 address; no DNS names')
    if ip.is_unspecified or ip.is_multicast or (ip.version == 4 and str(ip) == '255.255.255.255'):
        raise ValueError('unspecified, multicast or broadcast destination rejected')
    if not ip.is_global and not ip.is_loopback:
        raise ValueError('D03 standalone requires a globally routable IP (or loopback for local acceptance)')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('TCP port must be 1..65535')
    return str(ip), port, ip.version


def diagnostic_route(address, version):
    """Read-only route-table hint, not a proof of an effective packet path."""
    cmd = ['/sbin/route', '-n', 'get']
    if version == 6:
        cmd.append('-inet6')
    cmd.append(address)
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=3, check=False)
        if p.returncode or len(p.stdout) > 8192:
            return {'interface': None, 'available': False}
        m = re.search(r'(?m)^\s*interface:\s*([A-Za-z][A-Za-z0-9_.-]{0,63})\s*$',
                      p.stdout.decode('utf-8', 'replace'))
        return {'interface': m.group(1) if m else None, 'available': bool(m)}
    except (OSError, subprocess.TimeoutExpired):
        return {'interface': None, 'available': False}


def diagnostic_system_proxy():
    """Proxy status is a local hint; raw hostnames/PAC URLs are never stored."""
    try:
        from c_inventory import parse_proxy
        p = subprocess.run(['/usr/sbin/scutil', '--proxy'], capture_output=True,
                           timeout=3, check=False)
        if p.returncode or len(p.stdout) > 32768:
            return None
        return parse_proxy(p.stdout.decode('utf-8', 'replace'))['enabled']
    except (OSError, subprocess.TimeoutExpired, ImportError):
        return None


def tcp_connect(address, port, family, timeout=TIMEOUT_SEC):
    """One kernel socket connect; clock starts immediately before connect()."""
    sock = None
    started = None
    def elapsed_ms():
        return (time.perf_counter_ns() - started) / 1_000_000.0 if started is not None else 0.0
    try:
        sock = socket.socket(socket.AF_INET if family == 4 else socket.AF_INET6, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        started = time.perf_counter_ns()
        sock.connect((address, port))
        return elapsed_ms(), None
    except socket.timeout:
        return elapsed_ms(), 'timeout'
    except ConnectionRefusedError:
        return elapsed_ms(), 'refused'
    except OSError as exc:
        if getattr(exc, 'errno', None) in (51, 65, 101, 113):
            code = 'unreachable'
        else:
            code = 'connect_error'
        return elapsed_ms(), code
    finally:
        if sock is not None:
            sock.close()


def percentile(values, percent):
    """Linear interpolation on the sorted successful-connect samples."""
    if not values:
        return None
    data = sorted(values)
    r = (len(data) - 1) * percent / 100.0
    i = math.floor(r)
    j = math.ceil(r)
    return round(data[i] + (data[j] - data[i]) * (r - i), 3)


def execute(address, port, profile, connector=tcp_connect, sleeper=time.sleep,
            route_reader=diagnostic_route, proxy_reader=diagnostic_system_proxy):
    ip, port, family = validate_endpoint(address, port)
    if profile not in PROFILES:
        raise ValueError('invalid measurement profile')
    count = PROFILES[profile]
    observations = []
    ok = []
    errors = {}
    started_ns = time.perf_counter_ns()
    for index in range(1, count + 1):
        elapsed, error = connector(ip, port, family, TIMEOUT_SEC)
        if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
            raise RuntimeError('invalid timer sample')
        if error not in (None, 'timeout', 'refused', 'unreachable', 'connect_error'):
            raise RuntimeError('invalid socket result')
        elapsed = round(elapsed, 3)
        observations.append({'index': index, 'success': error is None,
                             'elapsed_ms': elapsed, 'error_code': error})
        if error is None:
            ok.append(elapsed)
        else:
            errors[error] = errors.get(error, 0) + 1
        if index < count:
            sleeper(INTERVAL_SEC)
    p50 = percentile(ok, 50)
    p95 = percentile(ok, 95)
    metrics = {
        'sample_count': count,
        'successful_samples': len(ok),
        'failed_samples': count - len(ok),
        'success_pct': round(100.0 * len(ok) / count, 3),
        'tcp_connect_p50_ms': p50,
        'tcp_connect_p95_ms': p95,
        'tcp_connect_p99_ms': percentile(ok, 99),
        'p95_minus_p50_ms': round(p95 - p50, 3) if p95 is not None else None,
        'tcp_connect_min_ms': round(min(ok), 3) if ok else None,
        'tcp_connect_max_ms': round(max(ok), 3) if ok else None,
        'tcp_connect_stddev_ms': round(statistics.pstdev(ok), 3) if ok else None,
    }
    hints = {'target_route': route_reader(ip, family), 'system_proxy_enabled': proxy_reader(),
             'socket_uses_application_proxy': False,
             'effective_network_path_verified_direct': False}
    raw = {'source': 'python-stdlib-socket-connect', 'format_version': 1,
           'destination': {'ip': ip, 'port': port, 'ip_family': family},
           'profile': profile, 'connect_timeout_ms': int(TIMEOUT_SEC * 1000),
           'interval_ms': int(INTERVAL_SEC * 1000),
           'elapsed_run_ms': round((time.perf_counter_ns() - started_ns) / 1_000_000, 3),
           'attempts': observations, 'error_counts': errors,
           'route_and_proxy_hints': hints,
           'path_caveat': 'Kernel socket API does not prove traffic bypassed Network Extension/TUN/VPN or policy routing; route data is only a hint.'}
    return raw, metrics


def _write_json_new(path, obj):
    payload = (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    if len(payload) > MAX_JSON:
        raise RuntimeError('D03 output exceeds 256 KiB')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(str(path), flags, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(payload)


def handoff(raw, metrics):
    dest = raw['destination']
    num = metrics['successful_samples']
    total = metrics['sample_count']
    status = 'completed' if num == total else ('partial' if num else 'failed')
    tid = 'tcp-connect-ipv%d' % dest['ip_family']
    warnings = [{'code': 'PATH_UNVERIFIED',
                 'message': 'Socket connect is direct at application level, but TUN/VPN/transparent interception cannot be excluded.',
                 'test_id': tid}]
    if num < 100:
        warnings.append({'code': 'SPARSE_TAIL',
                         'message': 'Fewer than 100 successful connections; P99 is an unstable descriptive estimate.',
                         'test_id': tid})
    if num < total:
        warnings.append({'code': 'CONNECT_FAILURES',
                         'message': '%d of %d connection attempts failed.' % (total - num, total),
                         'test_id': tid})
    test = {'test_id': tid, 'attempt': 1, 'status': status,
            'evidence_scope': 'public_path' if not ipaddress.ip_address(dest['ip']).is_loopback else 'local',
            'data_provenance': 'observed',
            'tool': {'name': 'python-stdlib-socket', 'version': platform.python_version()},
            'network': {'ip_family': dest['ip_family'], 'transport': 'TCP',
                        'direction': 'C_TO_PUBLIC' if not ipaddress.ip_address(dest['ip']).is_loopback else 'LOCAL',
                        'proxy_mode': 'unknown'},
            'parameters': {'destination_ip': dest['ip'], 'destination_port': dest['port'],
                           'profile': raw['profile'], 'timeout_ms': raw['connect_timeout_ms'],
                           'interval_ms': raw['interval_ms'], 'proxy_requested': False,
                           'effective_path_verified': False},
            'metrics': metrics, 'raw_files': ['tcp-connect-attempts.json'],
            'errors': [], 'warnings': warnings}
    return {'contract_version': 1, 'synthetic': False, 'requested_tests': [tid],
            'tests': [test], 'raw_files': [{'path': 'tcp-connect-attempts.json',
                                          'format': 'json', 'test_id': tid}],
            'errors': [], 'warnings': []}, status


def main():
    try:
        ctx = validate_context('c-standalone')
    except (InvalidContext, OSError) as exc:
        print('[NetworkLab] c-standalone: SAFETY_BLOCKED (9): %s' % exc, file=sys.stderr)
        return 9
    if platform.system() != 'Darwin':
        print('[NetworkLab] c-standalone: DEPENDENCY_MISSING (4): macOS required', file=sys.stderr)
        return 4
    try:
        endpoint = ctx['effective_parameters'].get('tcp_endpoint')
        if not isinstance(endpoint, dict) or set(endpoint) != {'ip', 'port'}:
            raise ValueError('missing explicit TCP destination')
        raw, metrics = execute(endpoint['ip'], endpoint['port'], ctx['profile'])
        report, status = handoff(raw, metrics)
        work = Path(ctx['paths']['work_dir'])
        raw_dir = work / 'raw'
        raw_dir.mkdir(mode=0o700)
        _write_json_new(raw_dir / 'tcp-connect-attempts.json', raw)
        _write_json_new(work / 'worker-report.json', report)
    except (ValueError, OSError, RuntimeError) as exc:
        print('[NetworkLab] c-standalone: EXECUTION_FAILED (5): %s' % exc, file=sys.stderr)
        return 5
    if not ctx['quiet']:
        print('[NetworkLab] TCP %s:%d %s attempts=%d success=%.1f%% P50=%s P95=%s P99=%s; effective path UNVERIFIED' %
              (raw['destination']['ip'], raw['destination']['port'], status,
               metrics['sample_count'], metrics['success_pct'],
               metrics['tcp_connect_p50_ms'], metrics['tcp_connect_p95_ms'], metrics['tcp_connect_p99_ms']))
    return {'completed': 0, 'partial': 7, 'failed': 5}[status]


if __name__ == '__main__':
    sys.exit(main())
