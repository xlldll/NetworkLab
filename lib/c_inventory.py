#!/usr/bin/env python3
"""D02: macOS Client read-only network environment snapshot.

Uses built-in Apple command-line tools; never probes an external host, changes
settings, requests elevated privileges, starts VPNs or touches credentials.
Only allowlisted, structured fields enter the private B09 raw evidence.
"""
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

from module_entry import InvalidContext, validate_context

IFACE = re.compile(r'^[A-Za-z][A-Za-z0-9_.:@-]{0,63}$')
MAX_INTERFACES = 128
MAX_CAPTURE = 256 * 1024
COMMANDS = {
    'ifconfig': ('-a',),
    'networksetup': ('-listallhardwareports',),
    'route4': ('-n', 'get', 'default'),
    'route6': ('-n', 'get', '-inet6', 'default'),
    'dns': ('--dns',),
    'proxy': ('--proxy',),
    'sw_vers': ('-productVersion',),
}
BINARIES = {
    'ifconfig': ('/sbin/ifconfig',),
    'networksetup': ('/usr/sbin/networksetup',),
    'route4': ('/sbin/route',), 'route6': ('/sbin/route',),
    'dns': ('/usr/sbin/scutil',), 'proxy': ('/usr/sbin/scutil',),
    'sw_vers': ('/usr/bin/sw_vers',),
}


def command_output(name):
    """Local observation only. No shell, no user-provided command or remote host."""
    exe = next((p for p in BINARIES[name] if os.path.isfile(p) and os.access(p, os.X_OK)), None)
    if exe is None:
        # Fixed basenames are permitted for unusual macOS images.
        exe = shutil.which({'route4': 'route', 'route6': 'route',
                            'dns': 'scutil', 'proxy': 'scutil'}.get(name, name))
    if not exe:
        return None
    try:
        env = dict(os.environ, LC_ALL='C', LANG='C')
        p = subprocess.run([exe] + list(COMMANDS[name]), stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=6, check=False, env=env)
        if p.returncode or len(p.stdout) > MAX_CAPTURE or len(p.stderr) > MAX_CAPTURE:
            return None
        return p.stdout.decode('utf-8', 'replace')
    except (OSError, subprocess.TimeoutExpired):
        return None


def valid_address(text):
    try:
        value = ipaddress.ip_address(text.split('%', 1)[0])
        return str(value)
    except ValueError:
        return None


def hardware_ports(text):
    ports = {}
    if text is None:
        return ports
    port = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('Hardware Port:'):
            port = s.partition(':')[2].strip()[:96]
        elif s.startswith('Device:') and port:
            dev = s.partition(':')[2].strip()
            if IFACE.fullmatch(dev):
                ports[dev] = port
    return ports


def parse_interfaces(text, ports):
    if text is None:
        raise RuntimeError('ifconfig -a unavailable')
    result = []
    current = None
    for line in text.splitlines():
        header = re.match(r'^([A-Za-z][A-Za-z0-9_.:@-]*):\s+flags=\d+<([^>]*)>\s+mtu\s+(\d+)', line)
        if header:
            name, flags, mtu = header.groups()
            if not IFACE.fullmatch(name):
                current = None
                continue
            if len(result) >= MAX_INTERFACES:
                raise RuntimeError('interface count exceeds safety limit')
            current = {'name': name, 'hardware_port': ports.get(name),
                       'is_up': 'UP' in flags.split(','), 'status': None,
                       'mtu_bytes': int(mtu), 'ipv4': [], 'ipv6': []}
            result.append(current)
            continue
        if current is None:
            continue
        s = line.strip()
        if s.startswith('status:'):
            current['status'] = s.partition(':')[2].strip()[:32]
        elif s.startswith('inet '):
            items = s.split()
            if len(items) >= 2:
                address = valid_address(items[1])
                if address and ':' not in address and len(current['ipv4']) < 32:
                    current['ipv4'].append(address)
        elif s.startswith('inet6 '):
            items = s.split()
            if len(items) >= 2:
                address = valid_address(items[1])
                if address and ':' in address and len(current['ipv6']) < 32:
                    current['ipv6'].append(address)
    if not result:
        raise RuntimeError('ifconfig returned no parseable interfaces')
    return result


def parse_route(text):
    if text is None:
        return {'interface': None, 'gateway': None, 'available': False}
    values = {}
    for line in text.splitlines():
        match = re.match(r'^\s*(interface|gateway):\s*(\S+)', line)
        if match:
            values[match.group(1)] = match.group(2)
    interface = values.get('interface')
    gateway = values.get('gateway')
    return {'interface': interface if interface and IFACE.fullmatch(interface) else None,
            'gateway': valid_address(gateway) if gateway else None,
            'available': bool(values)}


def parse_dns(text):
    if text is None:
        return {'available': False, 'resolvers': None}
    resolvers = []
    current = None
    for line in text.splitlines():
        if re.match(r'^resolver\s+#\d+', line.strip()):
            if len(resolvers) >= 64:
                break
            current = {'nameservers': [], 'if_index': None, 'flags': None}
            resolvers.append(current)
        if current is None:
            continue
        m = re.match(r'^\s*nameserver\[\d+\]\s*:\s*(\S+)', line)
        if m:
            address = valid_address(m.group(1))
            if address and len(current['nameservers']) < 16:
                current['nameservers'].append(address)
        m = re.match(r'^\s*if_index\s*:\s*(\d+)', line)
        if m:
            current['if_index'] = int(m.group(1))
        # Do not store sensitive domains, search suffixes, resolver order or URLs.
    return {'available': True, 'resolvers': resolvers}


def parse_proxy(text):
    keys = ('HTTPEnable', 'HTTPSEnable', 'SOCKSEnable',
            'ProxyAutoConfigEnable', 'ProxyAutoDiscoveryEnable', 'FTPEnable')
    if text is None:
        return {'available': False, 'enabled': None, 'protocols': {k: None for k in keys}}
    flags = {}
    for key in keys:
        m = re.search(r'(?m)^\s*' + re.escape(key) + r'\s*:\s*([01])\s*$', text)
        flags[key] = bool(int(m.group(1))) if m else None
    values = [x for x in flags.values() if x is not None]
    return {'available': True, 'enabled': any(values) if values else None,
            'protocols': flags}


def classify_connection(interfaces, route4):
    name = route4.get('interface')
    selected = next((x for x in interfaces if x['name'] == name), None)
    label = (selected.get('hardware_port') or '').lower() if selected else ''
    gateway = route4.get('gateway')
    if not selected:
        kind = 'unknown'
    elif name.startswith('utun'):
        kind = 'tunnel_default_route'
    elif 'iphone' in label:
        kind = 'iphone_usb_likely'
    elif 'wi-fi' in label or 'airport' in label:
        kind = 'wifi'
    elif 'ethernet' in label or 'lan' in label:
        kind = 'ethernet'
    else:
        kind = 'unknown'
    hint = ('iphone_tether_subnet_possible' if gateway == '172.20.10.1' else None)
    return {'ipv4_default_interface': name, 'kind_hint': kind,
            'hotspot_hint': hint, 'hotspot_confirmed': False,
            'reason': 'hardware-port/default-route heuristic only'}


def collect_snapshot(output=command_output, system=None):
    """Pure parser of allowlisted local command results; inject outputs in tests."""
    osname = system or platform.system()
    if osname != 'Darwin':
        raise RuntimeError('c-inventory requires macOS')
    captured = {name: output(name) for name in COMMANDS}
    ports = hardware_ports(captured['networksetup'])
    interfaces = parse_interfaces(captured['ifconfig'], ports)
    r4, r6 = parse_route(captured['route4']), parse_route(captured['route6'])
    dns, proxy = parse_dns(captured['dns']), parse_proxy(captured['proxy'])
    tun = sorted(x['name'] for x in interfaces if x['name'].startswith('utun'))
    ver = (captured['sw_vers'] or '').strip().splitlines()
    return {
        'snapshot_version': 1, 'source': 'local-macos-readonly',
        'os': {'system': 'Darwin', 'version': ver[0][:80] if ver else None,
               'architecture': platform.machine()},
        'network': {'interfaces': interfaces,
                    'default_routes': {'ipv4': r4, 'ipv6': r6},
                    'connection': classify_connection(interfaces, r4),
                    'ipv4_address_count': sum(len(x['ipv4']) for x in interfaces),
                    'ipv6_address_count': sum(len(x['ipv6']) for x in interfaces)},
        'dns': dns,
        'proxy': proxy,
        'tunnel': {'utun_interfaces_observed': tun,
                   'ipv4_default_uses_utun': r4['interface'].startswith('utun') if r4['interface'] else None,
                   'ipv6_default_uses_utun': r6['interface'].startswith('utun') if r6['interface'] else None,
                   'presence_does_not_prove_vpn_active': True},
        'public_network': {'external_ip': None, 'isp': None, 'asn': None,
                           'external_probe_performed': False},
        'limits': {'no_active_network_probe': True, 'no_root_required': True,
                   'no_wifi_ssid_or_mac_address_collected': True,
                   'system_proxy_not_proof_of_effective_traffic_path': True,
                   'hotspot_not_confirmed_without_external_evidence': True},
    }


def _write_json_new(path, obj):
    payload = (json.dumps(obj, ensure_ascii=False, sort_keys=True,
                          allow_nan=False, indent=2) + '\n').encode('utf-8')
    if len(payload) > MAX_CAPTURE:
        raise RuntimeError('D02 output exceeds 256 KiB safety bound')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(str(path), flags, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(payload)


def make_handoff(snapshot):
    net = snapshot['network']
    return {
        'contract_version': 1, 'synthetic': False,
        'requested_tests': ['c-local-environment'],
        'tests': [{
            'test_id': 'c-local-environment', 'attempt': 1, 'status': 'completed',
            'evidence_scope': 'local', 'data_provenance': 'observed',
            'tool': {'name': 'networklab-macos-inventory', 'version': '1'},
            'network': {'ip_family': None, 'transport': None, 'direction': 'LOCAL', 'proxy_mode': None},
            'parameters': {'method': 'macos-native-local-commands', 'active_network_probe': False},
            'metrics': {'interface_count': len(net['interfaces']),
                        'ipv4_address_count': net['ipv4_address_count'],
                        'ipv6_address_count': net['ipv6_address_count'],
                        'ipv4_default_interface': net['default_routes']['ipv4']['interface'],
                        'connection_kind_hint': net['connection']['kind_hint'],
                        'system_proxy_enabled': snapshot['proxy']['enabled'],
                        'ipv4_default_uses_utun': snapshot['tunnel']['ipv4_default_uses_utun'],
                        'dns_resolver_count': len(snapshot['dns']['resolvers']) if snapshot['dns']['resolvers'] is not None else None},
            'raw_files': ['c-local-environment.json'], 'errors': [], 'warnings': []}],
        'raw_files': [{'path': 'c-local-environment.json', 'format': 'json',
                       'test_id': 'c-local-environment'}],
        'errors': [], 'warnings': [],
    }


def main():
    try:
        ctx = validate_context('c-inventory')
    except (InvalidContext, OSError) as exc:
        print('[NetworkLab] c-inventory: SAFETY_BLOCKED (9): %s' % exc, file=sys.stderr)
        return 9
    if platform.system() != 'Darwin':
        print('[NetworkLab] c-inventory: DEPENDENCY_MISSING (4): macOS required', file=sys.stderr)
        return 4
    try:
        work = Path(ctx['paths']['work_dir'])
        raw = work / 'raw'
        raw.mkdir(mode=0o700)
        snapshot = collect_snapshot()
        _write_json_new(raw / 'c-local-environment.json', snapshot)
        _write_json_new(work / 'worker-report.json', make_handoff(snapshot))
    except (OSError, ValueError, RuntimeError) as exc:
        print('[NetworkLab] c-inventory: EXECUTION_FAILED (5): %s' % exc, file=sys.stderr)
        return 5
    if not ctx['quiet']:
        print('[NetworkLab] c-inventory: local snapshot captured (%s interfaces; no network probes)' %
              len(snapshot['network']['interfaces']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
