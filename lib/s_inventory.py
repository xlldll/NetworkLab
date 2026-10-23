#!/usr/bin/env python3
"""D01: Linux VPS local read-only inventory worker (Python >=3.8, stdlib only).

No outbound packets, privilege escalation, service changes or shell execution.
Worker publishes a bounded private raw snapshot and a B09 handoff. The existing
Runner/Report Writer owns the final schema, filenames and result publication.
"""
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import socket
import struct
import sys

from module_entry import InvalidContext, validate_context

SIOCGIFADDR = 0x8915  # Linux ioctl; never used outside Linux.
NAME = re.compile(r'^[A-Za-z0-9_.:@-]{1,64}$')
MAX_INTERFACES = 128


def bounded_text(path, limit=4096):
    """Read only a bounded regular proc/sys file; unavailable is None."""
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            return None
        return data.decode('utf-8', 'replace').strip()
    except (OSError, ValueError):
        return None


def distro_name(etc):
    raw = bounded_text(etc / 'os-release', 8192) or ''
    fields = {}
    for line in raw.splitlines():
        if '=' not in line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        if key in ('ID', 'VERSION_ID', 'PRETTY_NAME'):
            # Data, not shell syntax. Do not source or evaluate os-release.
            fields[key] = value.strip().strip('"')[:160]
    return fields


def linux_ipv4(ifname):
    """Kernel interface IPv4 address; no network connection is established."""
    if not NAME.fullmatch(ifname) or len(ifname.encode('utf-8')) > 15:
        return None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            data = fcntl.ioctl(s.fileno(), SIOCGIFADDR, struct.pack('256s', ifname.encode('ascii')))
        return str(ipaddress.IPv4Address(data[20:24]))
    except (OSError, UnicodeError, ValueError):
        return None


def linux_ipv6_map(proc):
    result = {}
    data = bounded_text(proc / 'net' / 'if_inet6', 1024 * 128)
    if data is None:
        return result
    for line in data.splitlines()[:1024]:
        fields = line.split()
        if len(fields) != 6 or not re.fullmatch('[0-9a-fA-F]{32}', fields[0]):
            continue
        try:
            addr = str(ipaddress.IPv6Address(int(fields[0], 16)))
            prefix = int(fields[2], 16)
        except ValueError:
            continue
        name = fields[5]
        if NAME.fullmatch(name):
            result.setdefault(name, []).append({'address': addr,
                                                  'prefix_length': prefix,
                                                  'scope_hex': fields[3]})
    return result


def interface_snapshot(sysroot, procroot, ipv4_lookup=linux_ipv4):
    netdir = sysroot / 'class' / 'net'
    if not netdir.is_dir():
        raise RuntimeError('Linux /sys/class/net unavailable')
    names = sorted(p.name for p in netdir.iterdir() if NAME.fullmatch(p.name))
    if len(names) > MAX_INTERFACES:
        raise RuntimeError('interface count exceeds safety limit')
    ipv6 = linux_ipv6_map(procroot)
    items = []
    for name in names:
        root = netdir / name
        mtu = bounded_text(root / 'mtu')
        speed = bounded_text(root / 'speed')
        v4 = ipv4_lookup(name)
        items.append({
            'name': name,
            'operstate': bounded_text(root / 'operstate'),
            'mtu_bytes': int(mtu) if mtu and mtu.isdecimal() else None,
            'link_speed_mbps_reported': int(speed) if speed and speed.isdecimal() else None,
            'ipv4_primary': v4,
            'ipv6_addresses': ipv6.get(name, []),
        })
    return items


def service_presence(procroot):
    """Visible process names, not a service health check. Empty does not imply stopped."""
    names = {'xray': 0, 'sing-box': 0, 'iperf3': 0}
    inspected = 0
    try:
        directories = (p for p in procroot.iterdir() if p.name.isdecimal() and p.is_dir())
        for folder in directories:
            if inspected >= 65536:
                break
            value = bounded_text(folder / 'comm', 128)
            if value is None:
                continue
            inspected += 1
            if value in names:
                names[value] += 1
    except OSError:
        pass
    return {'visible_process_counts': names, 'proc_entries_read': inspected,
            'is_service_health_check': False}


def collect_snapshot(proc=Path('/proc'), sysroot=Path('/sys'), etc=Path('/etc'),
                     ipv4_lookup=linux_ipv4, system=None):
    """Pure filesystem observation; alternate paths only for offline unit fixtures."""
    sysinfo = system or {'system': platform.system(), 'kernel': platform.release(),
                         'architecture': platform.machine(), 'cpu_count': os.cpu_count()}
    if sysinfo['system'] != 'Linux':
        raise RuntimeError('s-inventory requires Linux')
    interfaces = interface_snapshot(sysroot, proc, ipv4_lookup)
    osinfo = distro_name(etc)
    cpuinfo = bounded_text(proc / 'cpuinfo', 131072) or ''
    cpu_model = None
    for line in cpuinfo.splitlines():
        if line.lower().startswith(('model name\t', 'hardware\t', 'processor\t')) and ':' in line:
            cpu_model = line.split(':', 1)[1].strip()[:160] or None
            if cpu_model:
                break
    network = {'interfaces': interfaces,
               'ipv4_interface_count': sum(bool(x['ipv4_primary']) for x in interfaces),
               'ipv6_address_count': sum(len(x['ipv6_addresses']) for x in interfaces)}
    tcp = {
        'congestion_control': bounded_text(proc / 'sys/net/ipv4/tcp_congestion_control'),
        'available_congestion_controls': bounded_text(proc / 'sys/net/ipv4/tcp_available_congestion_control'),
        'default_qdisc': bounded_text(proc / 'sys/net/core/default_qdisc'),
        'tcp_rmem': bounded_text(proc / 'sys/net/ipv4/tcp_rmem'),
        'tcp_wmem': bounded_text(proc / 'sys/net/ipv4/tcp_wmem'),
    }
    return {'snapshot_version': 1, 'source': 'local-linux-readonly',
            'os': {'distribution': osinfo, 'kernel': sysinfo['kernel'],
                   'architecture': sysinfo['architecture'], 'cpu_logical': sysinfo['cpu_count'],
                   'cpu_model': cpu_model,
                   'virtualization_product_hint': bounded_text(sysroot / 'class/dmi/id/product_name', 256)},
            'network': network, 'tcp': tcp,
            'process_observation': service_presence(proc),
            'limits': {'no_active_network_probe': True, 'no_root_required': True,
                       'reported_link_speed_is_not_measured_throughput': True}}


def _write_json_new(path, value):
    """Exclusive file create in Runner's owned private working directory."""
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + '\n').encode('utf-8')
    if len(payload) > 256 * 1024:
        raise RuntimeError('D01 output exceeds 256 KiB safety bound')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(str(path), flags, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(payload)


def make_handoff(snapshot):
    interfaces = snapshot['network']['interfaces']
    return {
        'contract_version': 1, 'synthetic': False,
        'requested_tests': ['s-static'],
        'tests': [{
            'test_id': 's-static', 'attempt': 1, 'status': 'completed',
            'evidence_scope': 'local', 'data_provenance': 'observed',
            'tool': {'name': 'networklab-s-inventory', 'version': '1'},
            'network': {'ip_family': None, 'transport': None, 'direction': 'LOCAL', 'proxy_mode': None},
            'parameters': {'method': 'read-only-linux-os-proc-sys', 'active_network_probe': False},
            'metrics': {'interface_count': len(interfaces),
                        'ipv4_interface_count': snapshot['network']['ipv4_interface_count'],
                        'ipv6_address_count': snapshot['network']['ipv6_address_count'],
                        'cpu_logical': snapshot['os']['cpu_logical'],
                        'tcp_congestion_control': snapshot['tcp']['congestion_control'],
                        'default_qdisc': snapshot['tcp']['default_qdisc']},
            'raw_files': ['s-static.json'], 'errors': [], 'warnings': [],
        }],
        'raw_files': [{'path': 's-static.json', 'format': 'json', 'test_id': 's-static'}],
        'errors': [], 'warnings': [],
    }


def main():
    try:
        ctx = validate_context('s-inventory')
    except (InvalidContext, OSError) as exc:
        print('[NetworkLab] s-inventory: SAFETY_BLOCKED (9): %s' % exc, file=sys.stderr)
        return 9
    if platform.system() != 'Linux':
        print('[NetworkLab] s-inventory: DEPENDENCY_MISSING (4): Linux required', file=sys.stderr)
        return 4
    try:
        work = Path(ctx['paths']['work_dir'])
        raw = work / 'raw'
        raw.mkdir(mode=0o700)  # Reject pre-existing directory/symlink.
        snapshot = collect_snapshot()
        _write_json_new(raw / 's-static.json', snapshot)
        _write_json_new(work / 'worker-report.json', make_handoff(snapshot))
    except (OSError, ValueError, RuntimeError) as exc:
        print('[NetworkLab] s-inventory: EXECUTION_FAILED (5): %s' % exc, file=sys.stderr)
        return 5
    if not ctx['quiet']:
        print('[NetworkLab] s-inventory: local snapshot captured (%s interfaces, no network probes)' %
              len(snapshot['network']['interfaces']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
