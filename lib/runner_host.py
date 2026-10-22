#!/usr/bin/env python3
"""B05 module runner lifecycle host (no measurements, no final reports).

Python is used only for safe data parsing / subprocess management: macOS Bash
3.2 has no portable GNU timeout or portable JSON parser. No shell=True/eval.
The eventual B07/B08 validators and B09 Report Writer will replace the
narrow, read-only preflight and finalization stubs here.
"""
import argparse
import configparser
from datetime import datetime, timezone, timedelta
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

import server_config
import config_manager
import report

EXIT_USAGE, EXIT_CONFIG, EXIT_DEP, EXIT_FAILED = 2, 3, 4, 5
EXIT_TIMEOUT, EXIT_PARTIAL, EXIT_NI = 6, 7, 8
EXIT_SAFETY, EXIT_BUSY, EXIT_INT, EXIT_TERM = 9, 10, 130, 143
ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
SSH_ALIAS = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_.-]*$")
MODULES = {
    ('c', 'inventory'): 'c-inventory',
    ('c', 'standalone'): 'c-standalone',
    ('c', 'paired'): 'c-paired',
    ('c', 'proxy'): 'c-proxy',
    ('c', 'collect'): 'c-collect',
    ('s', 'inventory'): 's-inventory',
    ('s', 'toolbox'): 's-toolbox',
    ('s', 'service'): 's-service',
    ('s', 'schedule'): 's-scheduler',
}
PROFILES = {'quick', 'standard', 'deep'}
TOOL_IDS = ('netquality', 'tcpquality', 'hardwarequality', 'ipquality', 'nexttrace', 'mtr', 'flent')
# A06: all never silently opts in to possibly heavy benchmark tools.
DEFAULT_TOOLS = ('netquality', 'tcpquality', 'ipquality', 'nexttrace', 'mtr')
TZ8 = timezone(timedelta(hours=8))


class RunError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def validate_home():
    value = os.environ.get('NETLAB_HOME')
    if value is None:
        value = str(Path.home() / '.networklab')
    if not value or not os.path.isabs(value):
        raise RunError(EXIT_CONFIG, 'NETLAB_HOME must be a non-empty absolute path')
    return Path(value)


def cfg_read(path, explicit):
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    if not path.exists():
        if explicit:
            raise RunError(EXIT_CONFIG, 'configuration file not found: %s' % path)
        return parser
    if not path.is_file():
        raise RunError(EXIT_CONFIG, 'not a regular config file: %s' % path)
    try:
        with path.open('r', encoding='utf-8-sig') as fh:
            parser.read_file(fh)
    except (OSError, UnicodeError, configparser.Error) as exc:
        raise RunError(EXIT_CONFIG, 'cannot read configuration: %s' % exc)
    return parser


def validate_targets(path):
    # A05 fixed-eight-column data; no execution of arbitrary user config.
    if not path.is_file():
        raise RunError(EXIT_CONFIG, 'targets file not found: %s' % path)
    result = {}
    try:
        with path.open(encoding='utf-8-sig') as fh:
            rows = list(fh)
    except (OSError, UnicodeError) as exc:
        raise RunError(EXIT_CONFIG, 'cannot read targets: %s' % exc)
    for line_number, line in enumerate(rows, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        fields = [v.strip() for v in line.split('|')]
        if len(fields) != 8:
            raise RunError(EXIT_CONFIG, '%s:%s: expected 8 fields' % (path, line_number))
        name, tid, kind, v4, v6, perf, mtr, ssh = fields
        if not name or len(name) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise RunError(EXIT_CONFIG, '%s:%s: invalid display name' % (path, line_number))
        if not ID.fullmatch(tid) or tid in result:
            raise RunError(EXIT_CONFIG, '%s:%s: invalid/duplicate target_id' % (path, line_number))
        if kind not in ('nat', 'direct') or not (v4 or v6):
            raise RunError(EXIT_CONFIG, '%s:%s: invalid network mode/IP' % (path, line_number))
        try:
            if v4:
                ipaddress.IPv4Address(v4)
            if v6:
                if '%' in v6 or '[' in v6 or ']' in v6:
                    raise ValueError('scoped IPv6 not supported')
                ipaddress.IPv6Address(v6)
        except ValueError:
            raise RunError(EXIT_CONFIG, '%s:%s: invalid address' % (path, line_number))
        if any(not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 65535 for value in (perf, mtr)):
            raise RunError(EXIT_CONFIG, '%s:%s: invalid port' % (path, line_number))
        if ssh and not SSH_ALIAS.fullmatch(ssh):
            raise RunError(EXIT_CONFIG, '%s:%s: invalid SSH alias' % (path, line_number))
        result[tid] = {
            'display_name': name,
            'type': kind,
            'ipv4': v4 or None,
            'ipv6': v6 or None,
            'iperf3_external_tcp_port': int(perf),
            'tcp_mtr_port': int(mtr),
            'ssh_alias': ssh or None,
        }
    return result


def preflight(args, home):
    role = args.role
    cfg_path = Path(args.config).expanduser() if args.config else home / 'config' / ('c.conf' if role == 'c' else 's.conf')
    cfg = cfg_read(cfg_path, bool(args.config))
    try:
        default_profile = cfg.get('general', 'default_profile', fallback='standard').strip()
    except (ValueError, configparser.Error) as exc:
        raise RunError(EXIT_CONFIG, 'invalid general.default_profile: %s' % exc)
    if default_profile not in PROFILES:
        raise RunError(EXIT_CONFIG, 'invalid default_profile: %s' % default_profile)
    profile = args.profile or default_profile
    target, target_id, server_id = None, None, None
    if role == 'c' and args.command in ('paired', 'collect'):
        if not args.target:
            raise RunError(EXIT_USAGE, '%s requires a --target in this version' % args.command)
        targets_setting = cfg.get('paths', 'targets_file', fallback='targets.conf').strip()
        if not targets_setting:
            raise RunError(EXIT_CONFIG, 'paths.targets_file cannot be empty')
        targets_path = (cfg_path.parent / targets_setting).resolve()
        targets = validate_targets(targets_path)
        target = targets.get(args.target)
        if not target:
            raise RunError(EXIT_CONFIG, 'unknown target_id: %s' % args.target)
        target_id = args.target
    server_features = {}
    if role == 's':
        # B08: use precisely the same strict validator as `netlab-s config`.
        # Parsing S configuration is side-effect free; invalid configs cannot
        # reach a worker even when the worker is still a placeholder.
        try:
            server_model, _warnings = server_config.load(cfg_path)
        except config_manager.ConfigurationError as exc:
            raise RunError(exc.code, str(exc))
        server_id = server_model['server_id']
        default_profile = server_model['default_profile']
        profile = args.profile or default_profile
        server_features = {
            'tool_modes': server_config.effective_profile(server_model, profile),
            'limits': server_model['limits'],
            'enable_heavy_tests': server_model['enable_heavy_tests'],
            'scheduled_jobs': list(server_model['schedules']),
        }
    selected = []
    if args.command == 'toolbox':
        modules = args.modules or 'all'
        selected = list(DEFAULT_TOOLS if modules == 'all' else modules.split(','))
        if len(set(selected)) != len(selected) or any(m not in TOOL_IDS for m in selected):
            raise RunError(EXIT_USAGE, 'invalid --modules')
    return dict(config_path=str(cfg_path.resolve()), profile=profile, target=target,
                target_id=target_id, server_id=server_id, selected=selected, server_features=server_features)


def safe_module_path(root, role, module):
    expected = root / role / (module + '.sh')
    # protect against symlink escaping the app and arbitrary module strings
    canonical = expected.resolve()
    if not os.path.commonpath((str(root.resolve()), str(canonical))) == str(root.resolve()):
        raise RunError(EXIT_SAFETY, 'module path escapes app directory')
    return expected


def marker_placeholder(path):
    if not path.is_file():
        return True
    try:
        with path.open('rb') as fh:
            return b'NETLAB_IMPLEMENTED_V1' not in fh.read(512)
    except OSError:
        raise RunError(EXIT_FAILED, 'cannot inspect module')


def make_private_run(home, args, effective):
    os.umask(0o077)
    tempbase = home / 'tmp'
    if tempbase.is_symlink():
        raise RunError(EXIT_SAFETY, 'temporary root must not be a symlink')
    when = datetime.now(TZ8)
    scope = effective['target_id'] or effective['server_id'] or 'local'
    base_id = '%s-%s' % (when.strftime('%Y-%m-%d-%H-%M-%S'), scope)
    try:
        tempbase.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Atomic mkdir reserves the human-readable run_id across concurrent Runs.
        # B09 will also reserve final report filenames when report writing is added.
        for number in range(100):
            run_id = base_id + ('-%02d' % number if number else '')
            work = tempbase / ('run-' + run_id)
            try:
                work.mkdir(mode=0o700)
                break
            except FileExistsError:
                continue
        else:
            raise RunError(EXIT_BUSY, 'too many same-second Runs for %s' % scope)
    except OSError as exc:
        raise RunError(EXIT_FAILED, 'unable to create private workspace: %s' % exc)
    context = {
        'contract_version': 1,
        'role': args.role.upper(),
        'module_id': args.module,
        'run_id': run_id,
        'run_uuid': str(uuid.uuid4()),
        'correlation_id': None,
        'task_kind': 'transfer' if args.command == 'collect' else ('management' if args.command in ('service', 'schedule') else 'measurement'),
        'profile': effective['profile'],
        'target_id': effective['target_id'],
        'server_id': effective['server_id'],
        'selected_modules': effective['selected'],
        'non_interactive': args.non_interactive,
        'quiet': args.quiet,
        'started_at': when.isoformat(timespec='seconds'),
        'paths': {
            'result_root': str(Path(args.output_dir).expanduser().absolute()) if args.output_dir else str((home / 'results').absolute()),
            'work_dir': str(work),
        },
        'target': effective['target'],
        'effective_parameters': {'action': args.action or None, 'id': args.id or None,
                                 'server_config': effective.get('server_features', {})},
    }
    context_path = work / 'context.json'
    try:
        with context_path.open('x', encoding='utf-8') as fh:
            json.dump(context, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        context_path.chmod(0o600)
    except OSError as exc:
        raise RunError(EXIT_FAILED, 'unable to write Context: %s' % exc)
    return work, context_path


class Lifecycle:
    def __init__(self):
        self.cancel = 0
        self.child = None

    def on_int(self, _signum, _frame):
        self.cancel = EXIT_INT

    def on_term(self, _signum, _frame):
        self.cancel = EXIT_TERM

    def stop_group(self):
        if self.child is None or self.child.poll() is not None:
            return
        try:
            os.killpg(self.child.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.child.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.child.wait()


def pump(source, destination, logfile, quiet):
    # Line-oriented streaming is adequate for B05 scaffolding; no limits imposed
    # on workers' future binary files (those must use the private workspace).
    try:
        while True:
            block = source.readline()
            if not block:
                break
            logfile.write(block)
            logfile.flush()
            if not quiet:
                destination.buffer.write(block)
                destination.flush()
    except (BrokenPipeError, OSError):
        pass


def run_worker(args, effective, home, worker):
    monotonic_start = time.monotonic()
    work, context_path = make_private_run(home, args, effective)
    env = dict(os.environ)
    env.update(NETLAB_INTERNAL_WORKER='1', NETLAB_CONTEXT_FILE=str(context_path), NETLAB_WORK_DIR=str(work))
    lifecycle = Lifecycle()
    old_int = signal.signal(signal.SIGINT, lifecycle.on_int)
    old_term = signal.signal(signal.SIGTERM, lifecycle.on_term)
    rc = EXIT_FAILED
    try:
        with (work / 'stdout.log').open('wb') as fout, (work / 'stderr.log').open('wb') as ferr:
            try:
                child = subprocess.Popen(['bash', str(worker)], env=env, cwd=str(work),
                                         stdin=subprocess.DEVNULL if args.non_interactive else None,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         start_new_session=True)
            except OSError as exc:
                raise RunError(EXIT_FAILED, 'cannot launch worker: %s' % exc)
            lifecycle.child = child
            threads = [
                threading.Thread(target=pump, args=(child.stdout, sys.stdout, fout, args.quiet), daemon=True),
                threading.Thread(target=pump, args=(child.stderr, sys.stderr, ferr, False), daemon=True),
            ]
            for thread in threads:
                thread.start()
            deadline = time.monotonic() + args.timeout_seconds
            while child.poll() is None:
                if lifecycle.cancel:
                    rc = lifecycle.cancel
                    lifecycle.stop_group()
                    break
                if time.monotonic() >= deadline:
                    rc = EXIT_TIMEOUT
                    lifecycle.stop_group()
                    break
                try:
                    child.wait(timeout=0.075)
                except subprocess.TimeoutExpired:
                    pass
            else:
                rc = child.returncode
            for thread in threads:
                thread.join(timeout=2)
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
    # A07/B09: worker controls only its handoff, Report Writer controls publication.
    # Legacy test fixtures without a handoff remain report-free; placeholders never
    # produce official measurements. Keep work intact if publication fails.
    try:
        with context_path.open(encoding='utf-8') as stream:
            run_context = json.load(stream)
        published = report.finalize(run_context, work, rc, monotonic_start)
        if published is not None:
            report_path, rc = published
            report.verify_manifest(report_path)
            if not args.quiet:
                print('[NetworkLab] report: %s' % report_path)
    except (report.ReportError, OSError, ValueError) as exc:
        print('[NetworkLab] REPORT_ERROR (5): %s; private workspace retained: %s' %
              (exc, work), file=sys.stderr)
        return EXIT_FAILED
    if rc == EXIT_INT:
        print('[NetworkLab] INTERRUPTED (130); provisional workspace: %s' % work, file=sys.stderr)
    elif rc == EXIT_TERM:
        print('[NetworkLab] TERMINATED (143); provisional workspace: %s' % work, file=sys.stderr)
    elif rc == EXIT_TIMEOUT:
        print('[NetworkLab] TIMEOUT (6); provisional workspace: %s' % work, file=sys.stderr)
    elif rc == EXIT_NI:
        print('[NetworkLab] %s: NOT_IMPLEMENTED (8)' % args.module, file=sys.stderr)
    elif rc == 0:
        if not args.quiet:
            print('[NetworkLab] %s worker exited 0 (no worker-report.json; no official measurement report)' % args.module)
    else:
        print('[NetworkLab] %s worker exit=%s; provisional workspace: %s' % (args.module, rc, work), file=sys.stderr)
    return rc


def build_parser():
    parser = argparse.ArgumentParser(description='NetworkLab B05 Runner internal entry')
    parser.add_argument('--root', required=True)
    parser.add_argument('--role', choices=('c', 's'), required=True)
    parser.add_argument('--command', required=True)
    parser.add_argument('--module', required=True)
    parser.add_argument('--action', default='')
    parser.add_argument('--id', default='')
    parser.add_argument('--config', default='')
    parser.add_argument('--profile', choices=('quick', 'standard', 'deep'), default='')
    parser.add_argument('--target', default='')
    parser.add_argument('--modules', default='')
    parser.add_argument('--output-dir', default='')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--non-interactive', action='store_true')
    # Internal watchdog for development; module-specific profile budgets are B08.
    parser.add_argument('--timeout-seconds', type=float, default=60.0)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if MODULES.get((args.role, args.command)) != args.module:
        print('[NetworkLab] SAFETY_BLOCKED (9): unregistered module', file=sys.stderr)
        return EXIT_SAFETY
    if not (0 < args.timeout_seconds <= 3600):
        print('[NetworkLab] USAGE_ERROR (2): invalid watchdog', file=sys.stderr)
        return EXIT_USAGE
    try:
        home = validate_home()
        effective = preflight(args, home)
        worker = safe_module_path(Path(args.root), args.role, args.module)
        if marker_placeholder(worker):
            print('[NetworkLab] %s: NOT_IMPLEMENTED (8)%s' % (
                args.module, '; dry-run has no executable plan' if args.dry_run else ''), file=sys.stderr)
            return EXIT_NI
        if args.dry_run:
            # After B06, implemented modules may furnish a structured preview.
            print('[NetworkLab] %s: dry-run plan unavailable in B05 (8)' % args.module, file=sys.stderr)
            return EXIT_NI
        return run_worker(args, effective, home, worker)
    except RunError as exc:
        label = {EXIT_CONFIG: 'CONFIG_ERROR', EXIT_SAFETY: 'SAFETY_BLOCKED',
                 EXIT_USAGE: 'USAGE_ERROR', EXIT_FAILED: 'EXECUTION_FAILED',
                 EXIT_BUSY: 'BUSY'}.get(exc.code, 'ERROR')
        print('[NetworkLab] %s (%s): %s' % (label, exc.code, exc), file=sys.stderr)
        return exc.code


if __name__ == '__main__':
    sys.exit(main())
