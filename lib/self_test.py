#!/usr/bin/env python3
"""B11 offline skeleton self-test. Never edits live app, configs, or results.

A temporary minimal copy of NetworkLab runs synthetic workers only. No real
network benchmarking, SSH connection, system changes, or external packages.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
import report


class SelfTestError(Exception):
    pass


def ensure(condition, explanation):
    if not condition:
        raise SelfTestError(explanation)


def call(argv, env, timeout=12):
    try:
        return subprocess.run(argv, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=timeout,
                              check=False)
    except subprocess.TimeoutExpired:
        raise SelfTestError('subprocess timed out: %s' % argv[1:3])
    except OSError as exc:
        raise SelfTestError('cannot start subprocess: %s' % exc)


def check_rc(proc, expected, name):
    if proc.returncode != expected:
        tail = (proc.stderr or proc.stdout or '').strip()[-450:]
        raise SelfTestError('%s: expected exit %s, got %s; %s' % (
            name, expected, proc.returncode, tail))


def make_isolated_copy(source, destination):
    # The test fixture MUST NOT modify the checked-out repository.
    for folder in ('lib', 'c', 's', 'schemas'):
        origin = source / folder
        ensure(origin.is_dir() and not origin.is_symlink(), 'missing or linked directory: ' + folder)
        (destination / folder).mkdir(mode=0o700)
        for item in origin.iterdir():
            if (item.is_file() and not item.is_symlink() and
                item.suffix in ('.sh', '.py', '.json')):
                shutil.copyfile(item, destination / folder / item.name)
    for entry in ('netlab-c.sh', 'netlab-s.sh'):
        p = source / entry
        ensure(p.is_file() and not p.is_symlink(), 'missing entry script: ' + entry)
        shutil.copyfile(p, destination / entry)


def install_synthetic_worker(app, role):
    """Replaces inventory worker ONLY inside disposable test installation."""
    worker = app / role / ('%s-inventory.sh' % role)
    # Restrict worker's only outputs to its private NETLAB_WORK_DIR.
    worker.write_text('''#!/usr/bin/env bash
# NETLAB_IMPLEMENTED_V1 (B11 synthetic-only self-test fixture)
python3 -S - <<'PY_SYNTHETIC_WORKER'
import json, os
from pathlib import Path
work = Path(os.environ['NETLAB_WORK_DIR'])
raw = work / 'raw'
raw.mkdir(mode=0o700)
(raw / 'probe.json').write_text(json.dumps({'synthetic': True, 'value': 42}) + '\\n', encoding='utf-8')
test = {
    'test_id': 'probe', 'attempt': 1, 'status': 'completed',
    'evidence_scope': 'local', 'data_provenance': 'observed',
    'tool': {'name': 'networklab-self-test', 'version': '1.0'},
    'network': {'ip_family': None, 'transport': None, 'direction': 'LOCAL', 'proxy_mode': None},
    'parameters': {}, 'metrics': {'fixture_value': 42},
    'raw_files': ['probe.json'], 'errors': [], 'warnings': []
}
handoff = {
    'contract_version': 1, 'synthetic': True,
    'requested_tests': ['probe'], 'tests': [test],
    'raw_files': [{'path': 'probe.json', 'format': 'json', 'test_id': 'probe'}],
    'errors': [], 'warnings': []
}
(work / 'worker-report.json').write_text(json.dumps(handoff), encoding='utf-8')
print('NetworkLab SYNTHETIC fixture complete')
PY_SYNTHETIC_WORKER
''', encoding='utf-8')
    worker.chmod(0o700)


def sample_config(home):
    config = home / 'config'
    config.mkdir(parents=True, mode=0o700)
    (config / 'c.conf').write_text(
        '[general]\nconfig_version=1\ndefault_profile=standard\n'
        '[paths]\ntargets_file=targets.conf\n', encoding='utf-8')
    (config / 'targets.conf').write_text(
        'Synthetic VPS|netlab-fixture|direct|198.51.100.1||5202|443|fixture\n',
        encoding='utf-8')
    (config / 's.conf').write_text(
        '[general]\nconfig_version=1\nserver_id=selftest-vps\n'
        'timezone=UTC+08:00\ndefault_profile=quick\n', encoding='utf-8')


def validate_run(app, home, role):
    manifests = list((home / 'results' / role).rglob('%s-manifest-*.json' % role))
    ensure(len(manifests) == 1, '%s: expected one isolated manifest, got %d' % (role, len(manifests)))
    manifest_path = manifests[0]
    manifest = report.verify_manifest(manifest_path)
    ensure(manifest['synthetic'] is True, '%s: fixture was not marked synthetic' % role)
    ensure(manifest['role'] == role.upper(), '%s: wrong role' % role)
    ensure(manifest['status'] == 'completed', '%s: report not completed' % role)
    ensure(manifest['started_at'].endswith('+08:00'), '%s: timestamp not UTC+8' % role)
    ensure(manifest['scope_id'] == ('local' if role == 'c' else 'selftest-vps'),
           '%s: wrong report scope' % role)
    summary_name = next((item['path'] for item in manifest['files'] if item['kind'] == 'summary'), None)
    ensure(summary_name is not None, '%s: missing summary' % role)
    summary = report.load_json(manifest_path.parent / summary_name, report.MAX_SOURCE_SIZE)
    ensure(summary['synthetic'] is True and summary['run_uuid'] == manifest['run_uuid'],
           '%s: summary identity mismatch' % role)
    ensure(len(summary['tests']) == 1 and summary['tests'][0]['metrics']['fixture_value'] == 42,
           '%s: synthetic metrics mismatch' % role)
    raw_name = next((item['path'] for item in manifest['files'] if item['kind'] == 'raw'), None)
    ensure(raw_name is not None, '%s: missing raw evidence' % role)
    raw_path = manifest_path.parent / raw_name
    ensure(json.loads(raw_path.read_text(encoding='utf-8')) == {'synthetic': True, 'value': 42},
           '%s: raw fixture content mismatch' % role)
    return manifest_path, manifest, raw_path


def run_checks(source, role, quiet):
    checks = []
    watched = [source / 'netlab-c.sh', source / 'netlab-s.sh',
               source / 'lib' / 'runner.sh', source / 'lib' / 'self_test.py',
               source / 'c' / 'c-inventory.sh', source / 's' / 's-inventory.sh']
    before = {}
    for path in watched:
        ensure(path.is_file() and not path.is_symlink(), 'missing or linked application file: ' + path.name)
        before[path] = hashlib.sha256(path.read_bytes()).digest()

    def passed(name):
        checks.append(name)
        if not quiet:
            print('[PASS] ' + name)

    with tempfile.TemporaryDirectory(prefix='netlab-self-test-') as name:
        temp = Path(name)
        app, home = temp / 'app', temp / 'home'
        app.mkdir(mode=0o700)
        home.mkdir(mode=0o700)
        make_isolated_copy(source, app)
        sample_config(home)
        env = dict(os.environ)
        for variable in ('NETLAB_INTERNAL_WORKER', 'NETLAB_CONTEXT_FILE', 'NETLAB_WORK_DIR',
                         'NETLAB_LOG_FILE', 'BASH_ENV', 'ENV', 'PYTHONPATH'):
            env.pop(variable, None)
        env['NETLAB_HOME'] = str(home)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        client = ['bash', str(app / 'netlab-c.sh')]
        server = ['bash', str(app / 'netlab-s.sh')]
        current = client if role == 'c' else server

        for binary, label in ((client, 'C'), (server, 'S')):
            proc = call(binary + ['--help'], env)
            check_rc(proc, 0, label + ' help')
            ensure('NetworkLab' in proc.stdout, label + ': no help banner')
            check_rc(call(binary + ['--version'], env), 0, label + ' version')
        passed('CLI help and version (C/S)')

        for args, label in ((client + ['config', 'validate'], 'C config'),
                            (client + ['targets', 'validate'], 'C targets'),
                            (server + ['config', 'validate'], 'S config'),
                            (server + ['config', 'profiles'], 'S profiles')):
            check_rc(call(args, env), 0, label)
        passed('configuration parsers and effective profile')

        check_rc(call(current + ['inventory', '--non-interactive'], env), 8, 'placeholder')
        ensure(not (home / 'results').exists(), 'placeholder produced a fake report')
        passed('unimplemented worker produces no report')

        module = app / role / ('%s-inventory.sh' % role)
        # An environment toggle is not a valid Runner Context.
        guard_env = dict(env, NETLAB_INTERNAL_WORKER='1')
        check_rc(call(['bash', str(module)], guard_env), 9, 'worker context guard')
        passed('internal Context guard rejects unsanctioned entry')

        install_synthetic_worker(app, role)
        proc = call(current + ['inventory', '--non-interactive'], env)
        check_rc(proc, 0, 'synthetic Runner')
        passed('Runner launches synthetic worker')

        path, manifest, raw_path = validate_run(app, home, role)
        passed('UTC+8 / unique Run identity / summary / raw SHA-256')

        show = call(current + ['results', 'show', manifest['run_id']], env)
        check_rc(show, 0, 'result show')
        ensure('VERIFIED' in show.stdout and 'SYNTHETIC' in show.stdout,
               'result browser did not verify synthetic evidence')
        listing = call(current + ['results', 'list'], env)
        check_rc(listing, 0, 'result list')
        ensure(manifest['run_id'] in listing.stdout, 'result list did not find synthetic run')
        passed('result browser lists and verifies report')

        # The integrity failure is triggered ONLY on the temporary fixture data.
        raw_path.write_bytes(b'{"synthetic":true,"value":999}\n')
        try:
            report.verify_manifest(path)
        except report.ReportError:
            pass
        else:
            raise SelfTestError('SHA-256 failed to detect a synthetic raw-file modification')
        check_rc(call(current + ['results', 'show', manifest['run_id']], env), 5,
                 'tampered report refused by browser')
        passed('tampering detected and refused')

        ensure(app != source and (home / 'config').is_dir(), 'incorrect isolation paths')
        for source_file, digest in before.items():
            ensure(hashlib.sha256(source_file.read_bytes()).digest() == digest,
                   'self-test changed an installed application file: ' + source_file.name)
        passed('installed application files remain unchanged')
    # TemporaryDirectory deletes fixture manifest, fake worker, and sample configs.
    if quiet:
        print('[NetworkLab] SELF_TEST PASS (%s): %d checks; offline synthetic only' % (
            role.upper(), len(checks)))
    else:
        print('[NetworkLab] SELF_TEST PASS (%s): %d checks; no live data changed' % (
            role.upper(), len(checks)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--role', required=True, choices=('c', 's'))
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--non-interactive', action='store_true')
    args = parser.parse_args(argv)
    source = Path(args.root).resolve()
    try:
        ensure(source.is_dir(), 'NetworkLab application root does not exist')
        return run_checks(source, args.role, args.quiet)
    except (SelfTestError, report.ReportError, ValueError, OSError, KeyError, TypeError) as exc:
        print('[NetworkLab] SELF_TEST FAIL (5): %s' % exc, file=sys.stderr)
        return 5


if __name__ == '__main__':
    sys.exit(main())
