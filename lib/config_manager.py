#!/usr/bin/env python3
"""B07 NetworkLab C-side configuration management (stdlib only).

No shell evaluation, no network traffic, no changes to live configuration until
new content passes validation and is atomically replaced under an advisory lock.
"""
import argparse
import configparser
from contextlib import contextmanager
import fcntl
import ipaddress
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

EX_USAGE, EX_CONFIG, EX_DEP, EX_FAILED, EX_SAFETY = 2, 3, 4, 5, 9
ID = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$')
ALIAS = re.compile(r'^[A-Za-z0-9_.][A-Za-z0-9_.-]*$')
PROFILES = {'quick', 'standard', 'deep'}
ALLOWED_INI = {
    'general': {'config_version', 'default_profile'},
    'network': {'preferred_ip_family'},
    'proxy': {'protocol', 'host', 'port'},
    'paths': {'targets_file'},
}


class ConfigurationError(Exception):
    def __init__(self, msg, code=EX_CONFIG):
        super().__init__(msg)
        self.code = code


def fail(msg, code=EX_CONFIG):
    raise ConfigurationError(msg, code)


def safe_read(path):
    if path.is_symlink():
        fail('refusing symlinked configuration file: %s' % path, EX_SAFETY)
    if not path.is_file():
        fail('configuration file not found: %s' % path)
    try:
        return path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError) as exc:
        fail('cannot read %s: %s' % (path, exc))


def load_client_config(path):
    text = safe_read(path)
    parser = configparser.ConfigParser(interpolation=None, strict=True, inline_comment_prefixes=None)
    try:
        parser.read_string(text, source=str(path))
    except (configparser.Error, ValueError) as exc:
        fail('invalid INI in %s: %s' % (path, exc))
    problems = []
    if parser.defaults():
        problems.append('[DEFAULT] section is not supported')
    for section in parser.sections():
        if section not in ALLOWED_INI:
            problems.append('unknown section [%s]' % section)
        else:
            for key in parser.options(section):
                if key not in ALLOWED_INI[section]:
                    problems.append('unknown key [%s].%s' % (section, key))
    version = parser.get('general', 'config_version', fallback='').strip()
    if version != '1':
        problems.append('general.config_version must be 1')
    profile = parser.get('general', 'default_profile', fallback='standard').strip()
    if profile not in PROFILES:
        problems.append('general.default_profile must be quick|standard|deep')
    family = parser.get('network', 'preferred_ip_family', fallback='auto').strip()
    if family not in ('auto', '4', '6'):
        problems.append('network.preferred_ip_family must be auto|4|6')
    protocol = parser.get('proxy', 'protocol', fallback='http').strip()
    if protocol not in ('http', 'socks5'):
        problems.append('proxy.protocol must be http|socks5')
    host = parser.get('proxy', 'host', fallback='127.0.0.1').strip()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        problems.append('proxy.host must be a literal IPv4 or IPv6 address')
    port = parser.get('proxy', 'port', fallback='7890').strip()
    if not valid_port(port):
        problems.append('proxy.port must be within 1..65535')
    targets_file = parser.get('paths', 'targets_file', fallback='targets.conf').strip()
    if not targets_file or '\x00' in targets_file or '\n' in targets_file:
        problems.append('paths.targets_file must be a non-empty path')
    if problems:
        fail('invalid c.conf %s:\n - %s' % (path, '\n - '.join(problems)))
    return parser


def config_paths(home, override):
    if override:
        cfg = Path(override).expanduser()
    else:
        cfg = home / 'config' / 'c.conf'
    # No os.chdir or shell variable evaluation.
    parser = load_client_config(cfg)
    target_setting = parser.get('paths', 'targets_file', fallback='targets.conf').strip()
    target_path = Path(target_setting)
    if not target_path.is_absolute():
        target_path = cfg.parent / target_path
    return cfg, target_path


def valid_port(value):
    return bool(re.fullmatch(r'[0-9]{1,5}', value)) and 1 <= int(value, 10) <= 65535


def validate_line(fields, lineno, seen):
    errors = []
    if len(fields) != 8:
        return None, ['line %d: expected exactly 8 columns (found %d)' % (lineno, len(fields))]
    name, tid, kind, ipv4, ipv6, iperf, mtr, ssh = fields
    if not (1 <= len(name) <= 80) or any(ord(c) < 32 or ord(c) == 127 for c in name):
        errors.append('line %d: invalid display_name (1..80 characters)' % lineno)
    if not ID.fullmatch(tid):
        errors.append('line %d: invalid target_id' % lineno)
    elif tid in seen:
        errors.append('line %d: duplicate target_id %s (first line %d)' % (lineno, tid, seen[tid]))
    if kind not in ('nat', 'direct'):
        errors.append('line %d: type must be nat|direct' % lineno)
    if not (ipv4 or ipv6):
        errors.append('line %d: at least one of IPv4 or IPv6 is required' % lineno)
    for val, expected in ((ipv4, 4), (ipv6, 6)):
        if val:
            try:
                if expected == 6 and ('%' in val or '[' in val or ']' in val):
                    raise ValueError('scoped/bracketed address')
                if expected == 4:
                    ipaddress.IPv4Address(val)
                else:
                    ipaddress.IPv6Address(val)
            except ValueError:
                errors.append('line %d: invalid IPv%d address' % (lineno, expected))
    if not valid_port(iperf):
        errors.append('line %d: invalid iperf3 external TCP port' % lineno)
    if not valid_port(mtr):
        errors.append('line %d: invalid TCP MTR port' % lineno)
    if ssh and not ALIAS.fullmatch(ssh):
        errors.append('line %d: invalid SSH alias' % lineno)
    if not errors:
        seen[tid] = lineno
        return dict(zip(('display_name','target_id','type','ipv4','ipv6','iperf3_external_tcp_port','tcp_mtr_port','ssh_alias'), fields)), []
    return None, errors


def validate_target_text(text, pathlabel='targets.conf'):
    records = []
    warnings = []
    errors = []
    seen = {}
    for no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        fields = [s.strip() for s in line.split('|')]
        record, bad = validate_line(fields, no, seen)
        errors.extend(bad)
        if record:
            records.append(record)
            for family in ('ipv4', 'ipv6'):
                addr = record[family]
                if addr and not ipaddress.ip_address(addr).is_global:
                    warnings.append('line %d: %s address is not globally routable; connectivity unverified' % (no, family))
    if errors:
        fail('%s failed validation:\n - %s' % (pathlabel, '\n - '.join(errors)))
    return records, warnings


def read_targets(path):
    return validate_target_text(safe_read(path), str(path))


def ensure_private_parent(path):
    parent = path.parent
    if parent.is_symlink():
        fail('symlinked config directory refused: %s' % parent, EX_SAFETY)
    if not parent.is_dir():
        fail('configuration directory not found: %s' % parent)
    if path.is_symlink():
        fail('symlinked target file refused: %s' % path, EX_SAFETY)
    if path.exists() and not path.is_file():
        fail('targets path is not a regular file: %s' % path, EX_SAFETY)


@contextmanager
def locked(path):
    ensure_private_parent(path)
    lockfile = path.parent / ('.' + path.name + '.lock')
    if lockfile.is_symlink():
        fail('symlinked lock file refused', EX_SAFETY)
    old_umask = os.umask(0o077)
    try:
        fd = os.open(str(lockfile), os.O_CREAT | os.O_RDWR, 0o600)
    finally:
        os.umask(old_umask)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def atomic_commit(path, new_text, kind='targets'):
    # Validate again under lock before committing candidate data.
    if kind == 'targets':
        validate_target_text(new_text, str(path))
    ensure_private_parent(path)
    if path.exists() and path.is_symlink():
        fail('symlink refused', EX_SAFETY)
    old_text = safe_read(path) if path.exists() else None
    old_bytes = path.read_bytes() if path.exists() else None
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix='.' + path.name + '.tmp-', dir=str(path.parent))
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            out.write(new_text)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp_name, 0o600)
        if kind == 'config':
            load_client_config(Path(tmp_name))
        if old_text is not None and old_text != new_text:
            now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            backup = path.parent / ('.%s.backup-%s' % (path.name, now))
            # Backup the previous known-good config only after validating candidate.
            old_fd = os.open(str(backup), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(old_fd, 'wb') as out:
                out.write(old_bytes)
                out.flush()
                os.fsync(out.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
    except (OSError, UnicodeError) as exc:
        fail('atomic configuration update failed: %s' % exc, EX_FAILED)
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass


def interactive_add(values):
    fields = [
        ('display_name', '顯示名稱'), ('target_id', 'Target ID'),
        ('type', 'nat / direct'), ('ipv4', 'IPv4（可留空）'),
        ('ipv6', 'IPv6（可留空）'), ('iperf3_external_tcp_port', 'iperf3 外部 TCP 埠'),
        ('tcp_mtr_port', 'TCP MTR 埠'), ('ssh_alias', 'SSH alias（可留空）'),
    ]
    for key, label in fields:
        if values[key] is None:
            try:
                values[key] = input('%s: ' % label).strip()
            except EOFError:
                fail('interactive input cancelled', EX_USAGE)
    return values


def pick_editor(name):
    name = name or 'nano'
    if name not in ('nano', 'vim'):
        fail('editor must be nano or vim', EX_USAGE)
    executable = shutil.which(name)
    if not executable:
        fail('%s is not installed' % name, EX_DEP)
    return executable


def editor_update(path, name, kind):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        fail('editing requires a terminal (TTY)', EX_USAGE)
    executable = pick_editor(name)
    with locked(path):
        current = safe_read(path) if path.exists() else ''
        # A copy rather than the live configuration is edited.
        fd, candidate = tempfile.mkstemp(prefix='.' + path.name + '.edit-', dir=str(path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                fh.write(current)
            os.chmod(candidate, 0o600)
            completed = subprocess.run([executable, candidate], check=False)
            if completed.returncode:
                fail('editor exited with code %d; original preserved' % completed.returncode, EX_FAILED)
            try:
                modified = Path(candidate).read_text(encoding='utf-8-sig')
            except (OSError, UnicodeError) as exc:
                fail('cannot read editor candidate: %s' % exc)
            # Do not commit identical content; avoids needless backups/replacements.
            if modified == current:
                print('[NetworkLab] No changes to %s' % path)
                return
            atomic_commit(path, modified, kind=kind)
            print('[NetworkLab] Updated: %s' % path)
        finally:
            try:
                os.unlink(candidate)
            except FileNotFoundError:
                pass


def report_validation(records, warnings):
    for warning in warnings:
        print('[NetworkLab] WARNING: ' + warning, file=sys.stderr)
    print('[NetworkLab] VALID: %d target(s)' % len(records))


def main():
    a = argparse.ArgumentParser(description='NetworkLab B07 Client configuration manager')
    a.add_argument('--home', required=True)
    a.add_argument('--config', default='')
    a.add_argument('--group', required=True, choices=('targets', 'config'))
    a.add_argument('--action', required=True)
    a.add_argument('--id', default='')
    a.add_argument('--editor', default='')
    a.add_argument('--dry-run', action='store_true')
    a.add_argument('--non-interactive', action='store_true')
    a.add_argument('--quiet', action='store_true')
    for prop in ('name', 'add-id', 'type', 'ipv4', 'ipv6', 'iperf-port', 'mtr-port', 'ssh-alias'):
        a.add_argument('--' + prop, default=None)
    args = a.parse_args()
    try:
        home = Path(args.home)
        if not home.is_absolute():
            fail('NETLAB_HOME must be an absolute path')
        cfg, targets = config_paths(home, args.config)
        if args.group == 'config':
            if args.action == 'validate':
                if args.dry_run:
                    fail('--dry-run not valid with config validate', EX_USAGE)
                print('[NetworkLab] VALID c.conf: %s' % cfg)
                return 0
            if args.action == 'edit':
                if args.dry_run:
                    print('[NetworkLab] DRY_RUN editor %s %s' % (args.editor or 'nano', cfg))
                    return 0
                editor_update(cfg, args.editor, 'config')
                return 0
            fail('unsupported config operation', EX_USAGE)
        if args.action == 'validate':
            recs, warns = read_targets(targets)
            report_validation(recs, warns)
            return 0
        if args.action == 'list':
            recs, _ = read_targets(targets)
            if not args.quiet:
                print('NAME | TARGET_ID | TYPE | IPv4 | IPv6 | IPERF_TCP | TCP_MTR | SSH_ALIAS')
            for rec in recs:
                print(' | '.join(rec[k] or '-' for k in ('display_name','target_id','type','ipv4','ipv6','iperf3_external_tcp_port','tcp_mtr_port','ssh_alias')))
            return 0
        if args.action == 'show':
            recs, _ = read_targets(targets)
            match = next((x for x in recs if x['target_id'] == args.id), None)
            if match is None:
                fail('unknown target_id: %s' % args.id)
            for key, val in match.items():
                print('%s: %s' % (key, val or '(not configured)'))
            return 0
        if args.action == 'edit':
            if args.dry_run:
                print('[NetworkLab] DRY_RUN editor %s %s' % (args.editor or 'nano', targets))
                return 0
            editor_update(targets, args.editor, 'targets')
            return 0
        if args.action == 'add':
            fields = dict(display_name=args.name, target_id=args.add_id, type=args.type,
                          ipv4=args.ipv4, ipv6=args.ipv6,
                          iperf3_external_tcp_port=args.iperf_port,
                          tcp_mtr_port=args.mtr_port, ssh_alias=args.ssh_alias)
            if args.non_interactive:
                for key in ('display_name', 'target_id','type','iperf3_external_tcp_port','tcp_mtr_port'):
                    if not fields[key]:
                        fail('missing required field: %s' % key, EX_USAGE)
                if not (fields['ipv4'] or fields['ipv6']):
                    fail('at least one address required', EX_USAGE)
            else:
                if not sys.stdin.isatty():
                    fail('targets add needs TTY or --non-interactive', EX_USAGE)
                fields = interactive_add(fields)
            row = '|'.join(str(fields[key] or '').strip() for key in ('display_name','target_id','type','ipv4','ipv6','iperf3_external_tcp_port','tcp_mtr_port','ssh_alias'))
            # Data validation even in dry-run; no filesystem writes.
            validate_target_text(row + '\n', 'new target')
            if args.dry_run:
                previous = safe_read(targets) if targets.exists() else ''
                existing, _ = validate_target_text(previous, str(targets))
                if any(r['target_id'] == fields['target_id'] for r in existing):
                    fail('target_id already exists: %s' % fields['target_id'])
                print('[NetworkLab] DRY_RUN add: %s' % row)
                return 0
            with locked(targets):
                previous = safe_read(targets) if targets.exists() else ''
                existing, _ = validate_target_text(previous, str(targets))
                if any(r['target_id'] == fields['target_id'] for r in existing):
                    fail('target_id already exists: %s' % fields['target_id'])
                proposed = previous + ('\n' if previous and not previous.endswith('\n') else '') + row + '\n'
                validate_target_text(proposed, str(targets))
                atomic_commit(targets, proposed, kind='targets')
            print('[NetworkLab] Added: %s' % fields['target_id'])
            return 0
        fail('unsupported targets operation', EX_USAGE)
    except ConfigurationError as exc:
        names = {EX_USAGE:'USAGE_ERROR',EX_CONFIG:'CONFIG_ERROR',EX_DEP:'DEPENDENCY_MISSING',EX_FAILED:'FAILED',EX_SAFETY:'SAFETY_BLOCKED'}
        print('[NetworkLab] %s (%d): %s' % (names.get(exc.code,'ERROR'), exc.code, exc), file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        print('[NetworkLab] INTERRUPTED (130)', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
