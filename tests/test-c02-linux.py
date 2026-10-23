#!/usr/bin/env python3
"""C02: isolated Debian/Ubuntu Server acceptance without network tests or sudo.

Run on an actual Debian or Ubuntu VPS:
  python3 -B tests/test-c02-linux.py
Optional:
  python3 -B tests/test-c02-linux.py --keep

Uses a fresh temporary HOME/NETLAB_HOME. Does not modify ~/.networklab,
~/.local/bin, shell profiles, system services, or real VPS configuration.
Only exercises NetworkLab's offline install, stub execution, and self-test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
REQUIRED = (
    'install.sh', 'netlab-s.sh', 'netlab-c.sh',
    'lib/installer.py', 'lib/updater.py', 'lib/common.sh',
    'lib/self_test.py', 'lib/server_config.py',
    'defaults/s.conf', 'defaults/c.conf', 'defaults/targets.conf',
)

class Failure(Exception):
    pass


def check(condition, message):
    if not condition:
        raise Failure(message)
    print('[PASS] ' + message, flush=True)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def os_id():
    data = {}
    with open('/etc/os-release', encoding='utf-8') as handle:
        for line in handle:
            if '=' not in line or line.startswith('#'):
                continue
            k, v = line.rstrip('\n').split('=', 1)
            data[k] = v.strip().strip('"')
    return data.get('ID', '').lower(), data.get('VERSION_ID', 'unknown')


def run(argv, env, timeout=120):
    try:
        return subprocess.run([str(item) for item in argv], cwd=str(REPO), env=env,
                              input=None, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Failure('unable to finish %s: %s' % (argv, exc))


def succeeds(argv, env, label, timeout=120):
    proc = run(argv, env, timeout)
    if proc.returncode:
        raise Failure('%s exited %s\nstdout:\n%s\nstderr:\n%s' %
                      (label, proc.returncode, proc.stdout[-3500:], proc.stderr[-3500:]))
    return proc


def permissions_private(path):
    return not path.is_symlink() and (stat.S_IMODE(path.stat().st_mode) & 0o077) == 0


def acceptance(keep=False):
    if platform.system() != 'Linux':
        raise Failure('C02 must run on Linux. Use C01 on macOS.')
    distro, distro_version = os_id()
    if distro not in ('debian', 'ubuntu'):
        raise Failure('C02 sign-off requires Debian/Ubuntu, detected: %s. Alpine belongs to C03.' % distro)
    if os.geteuid() == 0:
        print('[C02] NOTE: running as root. This validates root HOME isolation, not ordinary-user permissions.', flush=True)
    if sys.version_info < (3, 8):
        raise Failure('Python >=3.8 required')
    check(shutil.which('bash') is not None, 'Bash available')
    check(shutil.which('python3') is not None, 'Python3 available')
    for path in REQUIRED:
        if not (REPO / path).is_file() or (REPO / path).stat().st_size == 0:
            raise Failure('source missing/empty: ' + path)
    check(True, 'B12/B13 source files present')

    temp_root = Path(tempfile.mkdtemp(prefix='networklab-c02-'))
    sandbox_home = temp_root / 'user'
    sandbox_home.mkdir(mode=0o700)
    lab = sandbox_home / '.networklab'
    env = dict(os.environ, HOME=str(sandbox_home), NETLAB_HOME=str(lab))
    for key in ('PYTHONPATH', 'NETLAB_INTERNAL_WORKER', 'NETLAB_CONTEXT',
                'NETLAB_WORKSPACE', 'NETLAB_SKIP_VALIDATION', 'NETLAB_LOG_FILE'):
        env.pop(key, None)
    try:
        preview = succeeds(['sh', REPO / 'install.sh', '--dry-run'], env, 'dry-run')
        check('role=s' in preview.stdout and not lab.exists(),
              'auto-role selects S on Linux; dry-run has no side effects')

        install = succeeds(['sh', REPO / 'install.sh'], env, 'first install')
        check('INSTALL PASS: S' in install.stdout, 'Server installation succeeded')
        launcher = lab / 'bin' / 'netlab-s'
        app = lab / 'app'
        sconf = lab / 'config' / 's.conf'
        check(all(p.exists() for p in (launcher, app / 'netlab-s.sh', sconf,
                                        lab / 'results', lab / 'logs')),
              'app, Server config, results, logs, and launcher initialized')
        check(not (lab / 'config/c.conf').exists() and
              not (lab / 'config/targets.conf').exists(),
              'Server-only installation did not create Client config')
        check(all(permissions_private(p) for p in
                  (lab, app, lab / 'config', sconf, lab / 'results', lab / 'logs', launcher)),
              'private permissions on application, config, data, and command')
        check(os.access(launcher, os.X_OK), 'netlab-s launcher is executable')
        match = re.search(r'(?m)^server_id\s*=\s*(s-[0-9a-f]{16})\s*$',
                          sconf.read_text(encoding='utf-8'))
        check(match is not None, 'auto-generated stable Server ID is valid')
        sid = match.group(1)

        for argv in (('--version',), ('--help',), ('config', 'validate'),
                     ('config', 'profiles'), ('self-test', '--non-interactive')):
            succeeds([launcher] + list(argv), env, 'launcher ' + ' '.join(argv))
        check(True, 'version, help, config, profiles, and 9-check Self-test pass')
        unknown = run([launcher, 'not-a-real-command'], env)
        check(unknown.returncode == 2, 'bad public CLI command returns usage code 2')
        placeholder = run([launcher, 'inventory', '--non-interactive'], env)
        check(placeholder.returncode == 8, 'unimplemented module returns code 8')
        check(not any((lab / 'results').rglob('*.json')),
              'placeholder did not publish fabricated reports')

        stored_log = lab / 'logs' / 'c02-retention-sentinel.log'
        stored_report = lab / 'results' / 'c02-retention-sentinel.txt'
        stored_log.write_text('log must survive reinstall\n', encoding='utf-8')
        stored_report.write_text('historical results must survive reinstall\n', encoding='utf-8')
        with sconf.open('a', encoding='utf-8') as fh:
            fh.write('\n# C02 retention sentinel\n')
        snapshot = {str(p): file_hash(p) for p in
                    (sconf, stored_log, stored_report, app / 'lib/common.sh')}
        again = succeeds(['sh', REPO / 'install.sh'], env, 'second install')
        check('preserved' in again.stdout and
              all(file_hash(Path(p)) == sha for p, sha in snapshot.items()),
              'repeat install preserves app, settings, logs, and reports')
        check(sid in sconf.read_text(encoding='utf-8'),
              'Server ID remains stable across reinstall')

        bad_source = lab / 'config' / 'update-source.json'
        bad_source.write_text(json.dumps({'github_repo': 'xlldll/NetworkLab'}) + '\n',
                              encoding='utf-8')
        bad_source.chmod(0o600)
        check(succeeds([launcher, 'update', 'apply', '--version', 'v0.1.1', '--dry-run'],
                       env, 'offline update preview').stdout.find('DRY_RUN') >= 0,
              'pinned update preview does not contact GitHub')
        check(all(file_hash(Path(p)) == sha for p, sha in snapshot.items()),
              'update preview did not modify app, settings, logs or reports')

        # Isolated, deliberately bad destination: should never follow links.
        hostile_home = temp_root / 'hostile'
        hostile_config = temp_root / 'outside'
        hostile_home.mkdir(mode=0o700)
        hostile_config.mkdir(mode=0o700)
        (hostile_home / 'config').symlink_to(hostile_config, target_is_directory=True)
        hostile_env = dict(env, NETLAB_HOME=str(hostile_home))
        unsafe = run(['sh', REPO / 'install.sh'], hostile_env)
        check(unsafe.returncode == 9 and not any(hostile_config.iterdir()),
              'symlinked configuration directory is rejected safely')
        print('\n[C02] DEBIAN/UBUNTU PASS: %s %s; isolated Server acceptance, no live network tests.' %
              (distro, distro_version), flush=True)
        print('[C02] This proves OS-local behavior only; true cross-version Release update remains separate.', flush=True)
    finally:
        if keep:
            print('[C02] Temporary acceptance directory retained: %s' % temp_root, flush=True)
        else:
            shutil.rmtree(temp_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keep', action='store_true',
                        help='retain isolated sandbox on failure/success for diagnosis')
    args = parser.parse_args()
    try:
        acceptance(args.keep)
        return 0
    except Failure as exc:
        print('[C02] FAIL: ' + str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
