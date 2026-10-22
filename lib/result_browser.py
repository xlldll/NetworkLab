#!/usr/bin/env python3
"""B10 read-only local results and logs browser (stdlib only).

Unverified values in `results list` are labelled as such. `results show`
verifies every indexed file via B09 before printing. No network or writes.
"""
import argparse
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import re
import stat
import sys

import report

EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_FAILED = 5
RUN_ID = re.compile(r'^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:-\d{2})?$')
LOG_EXTS = {'.log', '.txt', '.jsonl'}
MAX_ITEMS_SCANNED = 20000


class BrowserError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def regular_file(path):
    try:
        mode = path.lstat().st_mode
        return stat.S_ISREG(mode)
    except OSError:
        return False


def real_directory(path):
    try:
        mode = path.lstat().st_mode
        return stat.S_ISDIR(mode)
    except OSError:
        return False


def validate_root(path):
    p = Path(path).expanduser()
    if not p.is_absolute() or '..' in p.parts:
        raise BrowserError(EXIT_CONFIG, 'result root must be absolute without parent traversal')
    # Protect the directories directly controlled by NetworkLab. Avoid rejecting
    # macOS's legitimate /var -> /private/var global system alias.
    if p.exists() and not real_directory(p):
        raise BrowserError(EXIT_FAILED, 'results root must be a real directory')
    if p.parent.exists() and not real_directory(p.parent):
        raise BrowserError(EXIT_FAILED, 'results parent must be a real directory')
    return p


def directories(root, role):
    role_dir = root / role
    if role_dir.is_symlink():
        raise BrowserError(EXIT_FAILED, 'role directory must not be a symlink')
    if not role_dir.exists():
        return []
    if not real_directory(role_dir):
        raise BrowserError(EXIT_FAILED, 'role directory is not an ordinary directory')
    scopes = []
    try:
        for scope in role_dir.iterdir():
            if real_directory(scope):
                scopes.append(scope)
    except OSError as exc:
        raise BrowserError(EXIT_FAILED, 'cannot read results directory: %s' % exc)
    return scopes


def records(root, role):
    found = []
    for directory in directories(root, role):
        try:
            for path in directory.iterdir():
                if not path.name.startswith(role + '-manifest-') or not path.name.endswith('.json'):
                    continue
                if not regular_file(path):
                    continue
                found.append(path)
                if len(found) > MAX_ITEMS_SCANNED:
                    raise BrowserError(EXIT_FAILED, 'too many reports; refusing unbounded scan')
        except OSError as exc:
            raise BrowserError(EXIT_FAILED, 'cannot scan results: %s' % exc)
    return found


def read_stub(path, expected_role):
    try:
        obj = report.load_json(path, report.MAX_HANDOFF)
        if (not isinstance(obj, dict) or obj.get('report_type') != 'manifest' or
            not isinstance(obj.get('run_id'), str) or not RUN_ID.fullmatch(obj['run_id']) or
            obj.get('role', '').lower() != expected_role or
            obj.get('scope_id') != path.parent.name):
            raise ValueError('not a valid manifest header')
        started = datetime.fromisoformat(obj['started_at'])
        if started.tzinfo is None or started.utcoffset() != timedelta(hours=8):
            raise ValueError('timestamp must be UTC+08:00')
        return {'run_id': obj['run_id'], 'started': started, 'status': obj.get('status', 'unknown'),
                'scope': obj.get('scope_id', 'unknown'), 'synthetic': obj.get('synthetic', False),
                'path': path, 'valid_header': True}
    except (report.ReportError, ValueError, TypeError, KeyError, OverflowError) as exc:
        # A broken manifest remains visible by filename but is not trusted.
        return {'run_id': path.name, 'started': None, 'status': 'INVALID',
                'scope': path.parent.name, 'synthetic': None, 'path': path, 'valid_header': False}


def result_list(root, role, limit, quiet):
    rows = [read_stub(p, role) for p in records(root, role)]
    rows.sort(key=lambda r: (r['started'] or datetime.min.replace(tzinfo=timezone.utc),
                             r['path'].name), reverse=True)
    if not quiet:
        print('NetworkLab results (%s, newest first; metadata UNVERIFIED until show)' % role.upper())
    if not rows:
        print('No reports found.')
        return 0
    for r in rows[:limit]:
        if not r['valid_header']:
            print('INVALID  %s' % r['path'].name)
        else:
            print('%s  %-12s  %-15s  %-9s  %s' % (
                r['started'].isoformat(timespec='seconds'), r['status'], r['scope'],
                'SYNTHETIC' if r['synthetic'] else 'REAL', r['run_id']))
    return 0


def result_show(root, role, requested):
    if not RUN_ID.fullmatch(requested):
        raise BrowserError(EXIT_USAGE, 'RUN_ID must be a timestamp + scope ID, not a path')
    candidates = []
    for path in records(root, role):
        stub = read_stub(path, role)
        if stub['valid_header'] and stub['run_id'] == requested:
            candidates.append(path)
    if not candidates:
        raise BrowserError(EXIT_FAILED, 'RUN_ID not found: %s' % requested)
    if len(candidates) > 1:
        raise BrowserError(EXIT_FAILED, 'RUN_ID is ambiguous across results: %s' % requested)
    path = candidates[0]
    try:
        manifest = report.verify_manifest(path)
        if manifest['role'].lower() != role or manifest['run_id'] != requested:
            raise report.ReportError('role / run ID mismatch')
        summary_entries = [e for e in manifest['files'] if e['kind'] == 'summary']
        if len(summary_entries) != 1:
            raise report.ReportError('expected exactly one summary')
        summary = report.load_json(path.parent / summary_entries[0]['path'], report.MAX_SOURCE_SIZE)
    except (report.ReportError, OSError, KeyError, TypeError) as exc:
        raise BrowserError(EXIT_FAILED, 'integrity check failed: %s' % exc)
    print('Run ID:       %s' % manifest['run_id'])
    print('Run UUID:     %s' % manifest['run_uuid'])
    print('Module:       %s' % manifest['module_id'])
    print('Scope:        %s' % manifest['scope_id'])
    print('Status:       %s (exit %s)' % (manifest['status'], manifest['exit_code']))
    print('Started:      %s' % manifest['started_at'])
    print('Finished:     %s' % manifest['finished_at'])
    print('Profile:      %s' % manifest['profile'])
    print('Evidence:     %s' % ('SYNTHETIC / NOT REAL MEASUREMENT' if manifest['synthetic'] else 'NOT MARKED SYNTHETIC'))
    print('Integrity:    VERIFIED (SHA-256 + size + summary identity)')
    print('Tests:        %d' % len(summary['tests']))
    for t in summary['tests']:
        print('  %s #%s: %s, scope=%s, tool=%s' % (
            t['test_id'], t['attempt'], t['status'], t['evidence_scope'], t['tool']['name']))
    print('Indexed files:')
    for item in manifest['files']:
        print('  %-8s %10s bytes  %s' % (item['kind'], item['size_bytes'], item['path']))
    return 0


def log_list(home, root, role, limit, quiet):
    listing = []
    logdir = home / 'logs'
    if logdir.is_symlink():
        raise BrowserError(EXIT_FAILED, 'logs directory must not be a symlink')
    if logdir.exists():
        if not real_directory(logdir):
            raise BrowserError(EXIT_FAILED, 'logs path is not a directory')
        for p in logdir.iterdir():
            if p.suffix.lower() in LOG_EXTS and regular_file(p):
                listing.append((p.stat().st_mtime, 'operational', p.name))
    # Incomplete/failed workers can have logs without a valid final manifest.
    # Only list private workspace filenames; never read or print their contents.
    tmpdir = home / 'tmp'
    if tmpdir.is_symlink():
        raise BrowserError(EXIT_FAILED, 'workspace root must not be a symlink')
    if real_directory(tmpdir):
        for run_dir in tmpdir.iterdir():
            if not run_dir.name.startswith('run-') or not real_directory(run_dir):
                continue
            for basename in ('stdout.log', 'stderr.log'):
                log_path = run_dir / basename
                if regular_file(log_path):
                    listing.append((log_path.stat().st_mtime, 'work-' + basename.split('.')[0],
                                    'tmp/' + run_dir.name + '/' + basename))
    # Published stdout/stderr are included for visibility. Listing is metadata
    # only, never follows an indexed filename or renders raw output.
    for path in records(root, role):
        stub = read_stub(path, role)
        if not stub['valid_header']:
            continue
        try:
            obj = report.load_json(path, report.MAX_HANDOFF)
            for entry in obj.get('files', []):
                if not isinstance(entry, dict) or entry.get('kind') not in ('stdout', 'stderr'):
                    continue
                file_name = entry.get('path')
                if not isinstance(file_name, str) or not report.BASENAME.fullmatch(file_name):
                    continue
                log_file = path.parent / file_name
                if regular_file(log_file):
                    listing.append((log_file.stat().st_mtime, 'run-' + entry['kind'],
                                    path.parent.name + '/' + file_name))
        except (report.ReportError, OSError, TypeError, ValueError):
            continue
    listing.sort(key=lambda e: (-e[0], e[2]))
    if not quiet:
        print('NetworkLab logs (%s, newest first; listing only)' % role.upper())
    if not listing:
        print('No logs found.')
    else:
        for _, kind, name in listing[:limit]:
            print('%-12s %s' % (kind, name))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', required=True, choices=('c', 's'))
    parser.add_argument('--home', required=True)
    parser.add_argument('--group', required=True, choices=('results', 'logs'))
    parser.add_argument('--action', required=True, choices=('list', 'show'))
    parser.add_argument('--id', default='')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--output-dir', default='')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)
    try:
        home = Path(args.home).expanduser()
        if not home.is_absolute() or '..' in home.parts:
            raise BrowserError(EXIT_CONFIG, 'invalid NETLAB_HOME')
        if not 1 <= args.limit <= 999999:
            raise BrowserError(EXIT_USAGE, 'invalid --limit')
        if args.group == 'logs' and args.action != 'list':
            raise BrowserError(EXIT_USAGE, 'logs only supports list')
        root = validate_root(args.output_dir if args.output_dir else home / 'results')
        if args.group == 'results':
            if args.action == 'list':
                return result_list(root, args.role, args.limit, args.quiet)
            return result_show(root, args.role, args.id)
        return log_list(home, root, args.role, args.limit, args.quiet)
    except BrowserError as exc:
        print('[NetworkLab] %s (%s): %s' % ('USAGE_ERROR' if exc.code == 2 else 'BROWSER_ERROR', exc.code, exc), file=sys.stderr)
        return exc.code


if __name__ == '__main__':
    sys.exit(main())
