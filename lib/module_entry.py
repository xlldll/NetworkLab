#!/usr/bin/env python3
"""NetworkLab B06 internal module contract guard.

Public calls belong to netlab-c/netlab-s. A worker is entered only after Runner
creates a private per-run Context. This validates the handoff, but is *not*
security authorization: env vars and editable local files cannot confer rights.

No network, credential access, OS changes, or measurement functionality.
"""
import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

EXIT_SAFETY = 9
EXIT_NOT_IMPLEMENTED = 8
EXIT_FAILED = 5

MODULES = {
    'c-inventory': ('C', 'measurement'),
    'c-standalone': ('C', 'measurement'),
    'c-paired': ('C', 'measurement'),
    'c-proxy': ('C', 'measurement'),
    'c-collect': ('C', 'transfer'),
    's-inventory': ('S', 'measurement'),
    's-toolbox': ('S', 'measurement'),
    's-service': ('S', 'management'),
    's-scheduler': ('S', 'management'),
}
ID = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$')
RUN_ID = re.compile(r'^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[a-z0-9-]+(?:-\d{2})?$')


class InvalidContext(Exception):
    pass


def require(condition, message):
    if not condition:
        raise InvalidContext(message)


def no_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, 'duplicate JSON field')
        obj[key] = value
    return obj


def _protected_regular_file(path):
    # Reject a symlink, group/world-readable Context, non-owner files and FIFOs.
    mode = path.lstat()
    require(stat.S_ISREG(mode.st_mode), 'Context is not a regular file')
    require(mode.st_uid == os.geteuid(), 'Context owner mismatch')
    require(stat.S_IMODE(mode.st_mode) & 0o077 == 0, 'Context permissions are too broad')
    require(mode.st_size <= 262144, 'Context exceeds 256 KiB')


def _protected_directory(path):
    mode = path.lstat()
    require(stat.S_ISDIR(mode.st_mode), 'work directory is not a real directory')
    require(mode.st_uid == os.geteuid(), 'work directory owner mismatch')
    require(stat.S_IMODE(mode.st_mode) & 0o077 == 0, 'work directory permissions are too broad')


def validate_context(module_id, environ=None):
    """Return a checked in-memory context. Do not add privileged behavior here."""
    env = os.environ if environ is None else environ
    require(module_id in MODULES, 'unknown module')
    require(env.get('NETLAB_INTERNAL_WORKER') == '1', 'not a Runner worker')
    raw_dir = env.get('NETLAB_WORK_DIR', '')
    raw_file = env.get('NETLAB_CONTEXT_FILE', '')
    require(raw_dir and raw_file and os.path.isabs(raw_dir) and os.path.isabs(raw_file),
            'absolute Context and work paths required')
    work = Path(raw_dir)
    path = Path(raw_file)
    _protected_directory(work)
    _protected_regular_file(path)
    require(path == work / 'context.json', 'Context is not at the expected location')
    require(path.resolve(strict=True) == work.resolve(strict=True) / 'context.json',
            'Context path escapes work directory')

    try:
        # Explicit upper bound already checked before reading.
        with path.open('r', encoding='utf-8') as fh:
            context = json.load(fh, object_pairs_hook=no_duplicates)
    except (OSError, UnicodeError, ValueError) as exc:
        raise InvalidContext('unreadable or invalid Context JSON: %s' % exc)
    require(isinstance(context, dict), 'Context must be an object')
    role, expected_kind = MODULES[module_id]
    require(type(context.get('contract_version')) is int and context['contract_version'] == 1,
            'unsupported Context version')
    require(context.get('role') == role and context.get('module_id') == module_id,
            'module identity mismatch')
    require(context.get('task_kind') == expected_kind, 'task_kind mismatch')
    require(context.get('profile') in ('quick', 'standard', 'deep'), 'invalid profile')
    require(type(context.get('non_interactive')) is bool and
            type(context.get('quiet')) is bool, 'invalid interaction flags')
    rid = context.get('run_id')
    require(isinstance(rid, str) and len(rid) <= 125 and RUN_ID.fullmatch(rid),
            'invalid run_id')
    require(work.name == 'run-' + rid, 'Run working directory does not match ID')
    try:
        uid = uuid.UUID(context['run_uuid'])
        require(uid.version == 4 and str(uid) == context['run_uuid'], 'run_uuid must be UUIDv4')
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise InvalidContext('invalid run_uuid: %s' % exc)
    require(context.get('correlation_id') is None or isinstance(context.get('correlation_id'), str),
            'invalid correlation ID')
    try:
        timestamp = datetime.fromisoformat(context['started_at'])
        require(timestamp.utcoffset() == timedelta(hours=8), 'started_at must be UTC+08:00')
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidContext('invalid started_at: %s' % exc)
    paths = context.get('paths')
    require(isinstance(paths, dict), 'missing paths')
    require(paths.get('work_dir') == str(work), 'work path mismatch')
    require(isinstance(paths.get('result_root'), str) and os.path.isabs(paths['result_root']),
            'invalid results root')
    require(isinstance(context.get('effective_parameters'), dict), 'missing effective parameters')
    selected = context.get('selected_modules')
    require(isinstance(selected, list) and all(isinstance(t, str) for t in selected),
            'invalid selected_modules')
    require(isinstance(context.get('target_id'), (str, type(None))), 'invalid target_id')
    require(isinstance(context.get('server_id'), (str, type(None))), 'invalid server_id')
    if role == 'C':
        require(context['server_id'] is None, 'Client Context must not have server_id')
        if module_id in ('c-paired', 'c-collect'):
            require(isinstance(context.get('target_id'), str) and ID.fullmatch(context['target_id']),
                    'paired/collect requires target_id')
            require(isinstance(context.get('target'), dict), 'paired/collect requires target details')
        else:
            require(context['target_id'] is None, 'unexpected target_id')
            require(context.get('target') is None, 'unexpected target details')
    else:
        require(context['target_id'] is None and context.get('target') is None,
                'Server Context must not have client target')
        require(isinstance(context.get('server_id'), str) and ID.fullmatch(context['server_id']),
                'Server requires server_id')
    return context


def main(argv=None):
    parser = argparse.ArgumentParser(description='NetworkLab internal worker guard (B06)')
    parser.add_argument('--module-id', required=True, choices=sorted(MODULES))
    parser.add_argument('--validate-only', action='store_true',
                        help='internal compatibility helper for future worker implementations')
    args = parser.parse_args(argv)
    try:
        validate_context(args.module_id)
    except (InvalidContext, OSError) as exc:
        print('[NetworkLab] %s: SAFETY_BLOCKED (9): invalid internal Context: %s' %
              (args.module_id, exc), file=sys.stderr)
        return EXIT_SAFETY
    if args.validate_only:
        return 0  # Handoff validation only; never measurement completion.
    print('[NetworkLab] %s: NOT_IMPLEMENTED (8)' % args.module_id, file=sys.stderr)
    return EXIT_NOT_IMPLEMENTED


if __name__ == '__main__':
    sys.exit(main())
