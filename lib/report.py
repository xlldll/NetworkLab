#!/usr/bin/env python3
"""B09 A07-compatible, stdlib-only run report publisher.

This module is imported by runner_host only after a worker process ends.
Workers MAY write work/worker-report.json and work/raw/<basename>.
No handoff => no report. Not implemented => no report. Management => no report.
This is a REPORT SERIALIZER, not a synthetic measurement generator.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time

TZ8 = timezone(timedelta(hours=8))
ID = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$')
SLUG = re.compile(r'^[a-z0-9][a-z0-9-]*$')
BASENAME = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
UUID4 = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
HANDOFF = 'worker-report.json'
MAX_HANDOFF = 256 * 1024
MAX_SOURCE_SIZE = 256 * 1024 * 1024
VALID_STATUS = {'completed', 'failed', 'timeout', 'skipped', 'interrupted', 'partial', 'not_implemented'}
EVIDENCE = {'local', 'public_path', 'c_s_direct', 'proxy_path', 'third_party_service'}
PROVENANCE = {'observed', 'configured', 'provider_declared', 'unknown'}
DIRECTIONS = {'C_TO_S', 'S_TO_C', 'C_TO_PUBLIC', 'S_TO_PUBLIC', 'PROXY_TO_TARGET', 'LOCAL', None}
TRANSPORTS = {'TCP', 'UDP', 'ICMP', 'TLS', 'HTTP', 'QUIC', None}
EXIT_STATUS = {0: 'completed', 6: 'timeout', 7: 'partial', 8: 'not_implemented', 130: 'interrupted', 143: 'interrupted'}
SENSITIVE = re.compile(r'(authorization|cookie|password|passwd|secret|token|credential|private.?key|api.?key|access.?key|auth)', re.I)
SECRET_ASSIGNMENT = re.compile(r'(?i)(\b(?:authorization|cookie|password|passwd|secret|token|api[_-]?token|api[_-]?key|access[_-]?key)\b\s*[:=]\s*)[^\s,;]+')
AUTH_URL = re.compile(r'(?i)\b(?:https?|socks5?)://[^\s/@]+:[^\s/@]+@')


class ReportError(ValueError):
    """Report rejected. Caller must preserve work directory for inspection."""


def fail(message):
    raise ReportError(message)


def unique_object(pairs):
    out = {}
    for key, val in pairs:
        if key in out:
            fail('duplicate JSON key: %s' % key)
        out[key] = val
    return out


def load_json(path, size_limit):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > size_limit or path.stat().st_size < 1:
        fail('not a bounded regular JSON file: %s' % path.name)
    try:
        with path.open(encoding='utf-8') as f:
            return json.load(f, object_pairs_hook=unique_object,
                             parse_constant=lambda v: fail('nonfinite JSON: %s' % v))
    except (UnicodeError, OSError, ValueError) as e:
        fail('invalid JSON %s: %s' % (path.name, e))


def jsonbytes(obj):
    def check(value):
        if isinstance(value, float) and not math.isfinite(value):
            fail('NaN/Infinity are forbidden')
        if isinstance(value, dict):
            for v in value.values():
                check(v)
        if isinstance(value, (list, tuple)):
            for v in value:
                check(v)
    check(obj)
    return (json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False,
                       sort_keys=True) + '\n').encode('utf-8')


def redact(value):
    """Best-effort redaction; raw evidence requires worker-side privacy audit."""
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if SENSITIVE.search(str(k)) else redact(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return SECRET_ASSIGNMENT.sub(r'\1[REDACTED]', AUTH_URL.sub('[REDACTED-URL]', value))
    return value


def _safe_directory(path, create=False):
    path = Path(path)
    if path.is_symlink():
        fail('symlink directory rejected: %s' % path)
    if create:
        try:
            path.mkdir(mode=0o700, exist_ok=True)
        except OSError as exc:
            fail('cannot create output directory: %s' % exc)
    if not path.is_dir() or path.is_symlink():
        fail('not an ordinary output directory: %s' % path)
    return path


def result_directory(context):
    root = Path(context['paths']['result_root'])
    if not root.is_absolute() or '..' in root.parts:
        fail('invalid result root')
    # Do not traverse an attacker-supplied symlink as the result root.
    _safe_directory(root.parent)
    _safe_directory(root, create=True)
    role = context['role'].lower()
    scope = context['target_id'] if role == 'c' and context['module_id'] == 'c-paired' else (
        'proxy' if role == 'c' and context['module_id'] == 'c-proxy' else (
        'local' if role == 'c' else context['server_id']))
    if not isinstance(scope, str) or not ID.fullmatch(scope):
        fail('invalid scope_id')
    side = _safe_directory(root / role, create=True)
    out = _safe_directory(side / scope, create=True)
    return out, role, scope


def status_for(code):
    return EXIT_STATUS.get(code, 'failed')


def _errors(value, where):
    if not isinstance(value, list):
        fail('%s must be an array' % where)
    arr = []
    for e in value:
        if not isinstance(e, dict) or set(e) - {'code', 'message', 'test_id'}:
            fail('invalid error object')
        if not isinstance(e.get('code'), str) or not e['code'] or not isinstance(e.get('message'), str) or not e['message']:
            fail('invalid error message')
        if e.get('test_id') is not None and not isinstance(e['test_id'], str):
            fail('invalid test_id in error')
        arr.append(dict(code=e['code'], message=redact(e['message']), test_id=e.get('test_id')))
    return arr


def _safe_raw_name(name):
    if not isinstance(name, str) or not BASENAME.fullmatch(name) or name.startswith('.') or name.endswith('.'):
        fail('invalid raw filename')
    return name


def _test(test, allowed_raw):
    required = {'test_id', 'attempt', 'status', 'evidence_scope', 'data_provenance', 'tool',
                'network', 'parameters', 'metrics', 'raw_files', 'errors', 'warnings'}
    if not isinstance(test, dict) or set(test) != required:
        fail('test record must have precisely A07 fields')
    if not isinstance(test['test_id'], str) or not SLUG.fullmatch(test['test_id']):
        fail('invalid test_id')
    if type(test['attempt']) is not int or test['attempt'] < 1:
        fail('invalid attempt')
    if test['status'] not in VALID_STATUS or test['evidence_scope'] not in EVIDENCE or test['data_provenance'] not in PROVENANCE:
        fail('invalid test status/scope/provenance')
    tool = test['tool']
    if not isinstance(tool, dict) or set(tool) != {'name', 'version'} or not isinstance(tool['name'], str) or not tool['name'] or (tool['version'] is not None and not isinstance(tool['version'], str)):
        fail('invalid tool metadata')
    net = test['network']
    if not isinstance(net, dict) or set(net) != {'ip_family', 'transport', 'direction', 'proxy_mode'}:
        fail('invalid network metadata')
    if net['ip_family'] not in (4, 6, None) or type(net['ip_family']) is bool or net['transport'] not in TRANSPORTS or net['direction'] not in DIRECTIONS or net['proxy_mode'] not in ('direct', 'proxy', 'unknown', None):
        fail('invalid network values')
    if not isinstance(test['parameters'], dict) or not isinstance(test['metrics'], dict):
        fail('invalid parameters/metrics')
    names = test['raw_files']
    if not isinstance(names, list) or len(set(names)) != len(names) or not set(names).issubset(allowed_raw):
        fail('test references unindexed raw file')
    return dict(test_id=test['test_id'], attempt=test['attempt'], status=test['status'],
                evidence_scope=test['evidence_scope'], data_provenance=test['data_provenance'],
                tool=redact(tool), network=net, parameters=redact(test['parameters']),
                metrics=redact(test['metrics']), raw_files=names,
                errors=_errors(test['errors'], 'test errors'), warnings=_errors(test['warnings'], 'test warnings'))


def validate_handoff(handoff):
    if not isinstance(handoff, dict) or set(handoff) != {'contract_version', 'synthetic', 'requested_tests', 'tests', 'raw_files', 'errors', 'warnings'}:
        fail('worker-report.json fields do not match B09 contract')
    if type(handoff['contract_version']) is not int or handoff['contract_version'] != 1:
        fail('unknown handoff version')
    if type(handoff['synthetic']) is not bool:
        fail('synthetic flag is required')
    raw = handoff['raw_files']
    if not isinstance(raw, list):
        fail('raw_files must be array')
    names = set()
    cleaned = []
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {'path', 'format', 'test_id'}:
            fail('invalid raw_files record')
        name = _safe_raw_name(entry['path'])
        if name in names or entry['format'] not in {'json', 'ndjson', 'csv', 'txt', 'flent', 'binary', 'other'}:
            fail('duplicate raw file or invalid format')
        if entry['test_id'] is not None and (not isinstance(entry['test_id'], str) or not SLUG.fullmatch(entry['test_id'])):
            fail('invalid raw test_id')
        names.add(name)
        cleaned.append(entry)
    req = handoff['requested_tests']
    if not isinstance(req, list) or any(not isinstance(x, str) or not SLUG.fullmatch(x) for x in req) or len(req) != len(set(req)):
        fail('invalid requested_tests')
    if not isinstance(handoff['tests'], list):
        fail('tests must be array')
    tests = [_test(t, names) for t in handoff['tests']]
    if len({(t['test_id'], t['attempt']) for t in tests}) != len(tests):
        fail('duplicate test attempts')
    if any(t['test_id'] not in req for t in tests):
        fail('test not in requested_tests')
    if any(entry['test_id'] is not None and entry['test_id'] not in req for entry in cleaned):
        fail('raw test not in requested_tests')
    return dict(synthetic=handoff['synthetic'], requested_tests=req, tests=tests, raw_files=cleaned,
                errors=_errors(handoff['errors'], 'errors'), warnings=_errors(handoff['warnings'], 'warnings'))


def _copy_raw(src, dest, format_):
    import shutil
    if src.is_symlink() or not src.is_file():
        fail('unsafe raw source')
    meta = src.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid() or meta.st_nlink != 1 or meta.st_size > MAX_SOURCE_SIZE:
        fail('raw file size, type, hard link, or owner rejected')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(str(src), flags)
    with os.fdopen(fd, 'rb') as origin:
        before = os.fstat(origin.fileno())
        if before.st_ino != meta.st_ino or before.st_dev != meta.st_dev:
            fail('raw file changed during opening')
        if format_ == 'json' and before.st_size > 32 * 1024 * 1024:
            fail('JSON too large for validation')
        if format_ == 'json':
            load_json(src, 32 * 1024 * 1024)
        if format_ == 'ndjson':
            for line in origin:
                if line.strip():
                    try:
                        json.loads(line, object_pairs_hook=unique_object,
                                   parse_constant=lambda v: fail('nonfinite NDJSON'))
                    except (ValueError, UnicodeError):
                        fail('invalid NDJSON content')
            origin.seek(0)
        if format_ in ('txt', 'csv'):
            try:
                # Stream decode without materializing very large stdout files.
                import codecs
                dec = codecs.getincrementaldecoder('utf-8')()
                for block in iter(lambda: origin.read(65536), b''):
                    dec.decode(block)
                dec.decode(b'', final=True)
                origin.seek(0)
            except UnicodeError:
                fail('raw text must be UTF-8')
        _publish_stream(origin, dest)


def _publish_stream(src, dest):
    """Stage in same dir, fsync, publish via atomic no-clobber hard link."""
    parent = dest.parent
    fd, tmp = tempfile.mkstemp(prefix='.netlab-stage-', dir=str(parent))
    try:
        with os.fdopen(fd, 'wb') as dst:
            while True:
                chunk = src.read(65536)
                if not chunk:
                    break
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        os.chmod(tmp, 0o600)
        os.link(tmp, str(dest), follow_symlinks=False)
        _syncdir(parent)
    except FileExistsError:
        fail('refusing to overwrite existing report file: %s' % dest.name)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _publish_bytes(data, dest):
    import io
    _publish_stream(io.BytesIO(data), dest)


def _syncdir(path):
    if hasattr(os, 'O_DIRECTORY'):
        try:
            fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass  # macOS filesystem-dependent directory fsync


def _file_meta(path, kind, fmt, test_id=None):
    h = hashlib.sha256()
    size = 0
    with path.open('rb') as src:
        for block in iter(lambda: src.read(65536), b''):
            h.update(block)
            size += len(block)
    return dict(path=path.name, kind=kind, format=fmt, size_bytes=size,
                sha256=h.hexdigest(), test_id=test_id)


def _filename(role, test, scope, started, suffix, ext):
    return '%s-%s-%s-%s%s.%s' % (role, test, scope, started, suffix, ext)


def _start_info(context):
    when = datetime.fromisoformat(context['started_at'])
    rid = context['run_id']
    begin = when.strftime('%Y-%m-%d-%H-%M-%S') + '-' + (context['target_id'] or context['server_id'] or 'local')
    if rid == begin:
        return when.strftime('%Y-%m-%d-%H-%M-%S'), ''
    if re.fullmatch(re.escape(begin) + r'-\d{2}', rid):
        return when.strftime('%Y-%m-%d-%H-%M-%S'), rid[len(begin):]
    fail('run_id and timestamp mismatch')


def _lock_reservation(folder, run_id):
    lock = folder / ('.netlab-reservation-' + run_id)
    try:
        fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    except FileExistsError:
        fail('run already being published')
    return lock


def finalize(context, work, worker_rc, started_monotonic, networklab_version=None):
    """Publish only explicit worker handoff; return manifest path or None.

    The worker exit code is authoritative. A worker cannot assert completed if its
    process timed out or exited nonzero. Missing handoff is never fabricated.
    """
    if worker_rc == 8 or context['task_kind'] not in ('measurement', 'transfer'):
        return None
    handoff_path = work / HANDOFF
    if not handoff_path.exists():
        return None
    handoff = validate_handoff(load_json(handoff_path, MAX_HANDOFF))
    if not isinstance(context.get('run_uuid'), str) or not UUID4.fullmatch(context['run_uuid']):
        fail('invalid run_uuid')
    if context.get('correlation_id') is not None and (not isinstance(context['correlation_id'], str) or not UUID4.fullmatch(context['correlation_id'])):
        fail('invalid correlation_id')
    raw_dir = work / 'raw'
    if handoff['raw_files']:
        if raw_dir.is_symlink() or not raw_dir.is_dir() or raw_dir.lstat().st_uid != os.geteuid():
            fail('raw workspace directory must be an owned real directory')
    folder, role, scope = result_directory(context)
    stamp, suffix = _start_info(context)
    completed_at = datetime.now(TZ8).isoformat(timespec='seconds')
    duration = max(0, round((time.monotonic() - started_monotonic) * 1000))
    status = status_for(worker_rc)
    tests = handoff['tests']
    if status == 'completed' and (not handoff['requested_tests'] or
                                  {t['test_id'] for t in tests if t['status'] == 'completed'} != set(handoff['requested_tests']) or
                                  any(t['status'] != 'completed' for t in tests)):
        # Do not claim 100% success without all requested tests completed.
        status, worker_rc = 'partial', 7
    if worker_rc == 0 and not tests:
        fail('completed run without any test evidence')
    root_errors = handoff['errors']
    root_warnings = handoff['warnings']
    if status != 'completed':
        root_warnings = root_warnings + [dict(code='WORKER_STATUS', message='worker ended with exit code %s' % worker_rc,
                                              test_id=None)]
    if networklab_version is None:
        # Read the trusted installed source version, never an untrusted env var.
        raw_version = (Path(__file__).with_name('common.sh')).read_text('utf-8')
        match = re.search(r"(?m)^NETLAB_VERSION='([0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?)'$", raw_version)
        if match is None:
            fail('installed NetworkLab version unavailable')
        networklab_version = match.group(1)
    identity = dict(schema_version='1.0', synthetic=handoff['synthetic'], run_id=context['run_id'],
                    run_uuid=context['run_uuid'], correlation_id=context['correlation_id'],
                    role=context['role'], module_id=context['module_id'], scope_id=scope,
                    target_id=context['target_id'], server_id=context['server_id'],
                    profile=context['profile'], started_at=context['started_at'],
                    finished_at=completed_at, duration_ms=duration, status=status,
                    exit_code=worker_rc)
    # Public filenames are generated from already validated slugs, never from a user path.
    index = []
    raw_map = {}
    # Exclusive reservation prevents two processes from silently committing the same Run.
    lock = _lock_reservation(folder, context['run_id'])
    try:
        for entry in handoff['raw_files']:
            original = entry['path']
            ext = original.rsplit('.', 1)[-1] if '.' in original else 'bin'
            if not re.fullmatch('[a-z0-9]{1,12}', ext):
                ext = 'bin'
            stem = original.rsplit('.', 1)[0]
            # Normalize an arbitrary safe raw basename into the A07 test slug.
            slug = re.sub(r'[^a-z0-9-]+', '-', stem).strip('-')
            if not slug:
                fail('raw filename cannot be normalized into a test slug')
            name = _filename(role, slug, scope, stamp, suffix, ext)
            if name in raw_map.values():
                fail('two raw files map to same output filename')
            dest = folder / name
            _copy_raw(work / 'raw' / original, dest, entry['format'])
            raw_map[original] = name
            index.append(_file_meta(dest, 'raw', entry['format'], entry['test_id']))
        for test in tests:
            test['raw_files'] = [raw_map[p] for p in test['raw_files']]
        # Operational stdout/stderr copied as *redacted* text, never claimed native raw.
        for log in ('stdout', 'stderr'):
            path = work / (log + '.log')
            if path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 8 * 1024 * 1024:
                try:
                    text = path.read_text(encoding='utf-8')
                except UnicodeError:
                    root_warnings.append(dict(code='LOG_NOT_UTF8', message=log + ' omitted from public report', test_id=None))
                    continue
                public_name = _filename(role, log, scope, stamp, suffix, 'txt')
                _publish_bytes(redact(text).encode('utf-8'), folder / public_name)
                index.append(_file_meta(folder / public_name, log, 'txt'))
        # Stdout/stderr are operational logs, not the unmodified native raw format.
        # Do not silently publish potential secrets from arbitrary worker output.
        summary = dict(identity, report_type='summary', tests=tests,
                       errors=root_errors, warnings=root_warnings)
        summary_name = _filename(role, 'summary', scope, stamp, suffix, 'json')
        _publish_bytes(jsonbytes(summary), folder / summary_name)
        index.append(_file_meta(folder / summary_name, 'summary', 'json'))
        safe_params = {'selected_modules': list(context.get('selected_modules', [])),
                       'profile': context['profile'],
                       'action': context.get('effective_parameters', {}).get('action'),
                       'tool_modes': context.get('effective_parameters', {}).get('server_config', {}).get('tool_modes', {}),
                       'limits': context.get('effective_parameters', {}).get('server_config', {}).get('limits', {}),
                       'target_connection': context.get('target') if context.get('target_id') else None}
        manifest = dict(identity, report_type='manifest', task_kind=context['task_kind'],
                        networklab_version=networklab_version,
                        requested_tests=handoff['requested_tests'],
                        effective_parameters=redact(safe_params), files=index,
                        errors=root_errors, warnings=root_warnings)
        manifest_name = _filename(role, 'manifest', scope, stamp, suffix, 'json')
        _publish_bytes(jsonbytes(manifest), folder / manifest_name)
        return folder / manifest_name, worker_rc
    finally:
        lock.unlink(missing_ok=True)


def verify_manifest(manifest_path):
    """Check hashes and run identity. Does not authenticate provenance."""
    manifest_path = Path(manifest_path)
    manifest = load_json(manifest_path, MAX_HANDOFF)
    if not isinstance(manifest, dict) or manifest.get('report_type') != 'manifest':
        fail('not a manifest')
    files = manifest.get('files')
    if not isinstance(files, list) or not files:
        fail('manifest file index missing')
    summary = None
    seen = set()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {'path', 'kind', 'format', 'size_bytes', 'sha256', 'test_id'}:
            fail('bad file index')
        name = _safe_raw_name(entry['path'])
        if name in seen:
            fail('duplicate file path')
        seen.add(name)
        path = manifest_path.parent / name
        if path.is_symlink() or not path.is_file():
            fail('indexed file missing or symlink')
        actual = _file_meta(path, entry['kind'], entry['format'], entry['test_id'])
        if actual != entry:
            fail('hash or length mismatch: %s' % name)
        if entry['kind'] == 'summary':
            if summary is not None:
                fail('multiple summaries')
            summary = load_json(path, MAX_SOURCE_SIZE)
    if summary is None:
        fail('missing summary')
    for key in ('schema_version', 'synthetic', 'run_id', 'run_uuid', 'correlation_id', 'role',
                'module_id', 'scope_id', 'target_id', 'server_id', 'profile', 'started_at',
                'finished_at', 'duration_ms', 'status', 'exit_code'):
        if manifest.get(key) != summary.get(key):
            fail('manifest/summary mismatch: %s' % key)
    raw = {x['path'] for x in files if x['kind'] == 'raw'}
    for test in summary.get('tests', []):
        if not set(test['raw_files']).issubset(raw):
            fail('summary references unindexed raw file')
    return manifest
