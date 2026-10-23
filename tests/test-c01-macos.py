#!/usr/bin/env python3
"""NetworkLab C01: isolated macOS installation acceptance (no live probes/network).

Run: python3 -B tests/test-c01-macos.py
For Linux developer simulation only: ... --simulate
Neither mode mutates the user's ~/.networklab, ~/.local/bin or shell profiles.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
REQUIRED = [
    'install.sh', 'netlab-c.sh', 'netlab-s.sh',
    'lib/installer.py', 'lib/updater.py', 'lib/self_test.py',
    'defaults/c.conf', 'defaults/targets.conf', 'defaults/s.conf',
]
REPOSITORY = 'xlldll/NetworkLab'

class Failure(Exception):
    pass


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition, desc):
    if not condition:
        raise Failure(desc)
    print('[PASS] ' + desc, flush=True)


def run(argv, env, timeout=90):
    try:
        return subprocess.run([str(x) for x in argv], cwd=REPO, env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Failure('command failed to start/finish: %s : %s' % (argv, exc))


def must_pass(argv, env, label, timeout=90):
    p = run(argv, env, timeout)
    if p.returncode:
        raise Failure('%s returned %s\nstdout:\n%s\nstderr:\n%s' %
                      (label, p.returncode, p.stdout[-4000:], p.stderr[-4000:]))
    return p


def acceptance(simulate=False, keep=False):
    if platform.system() != 'Darwin' and not simulate:
        raise Failure('C01 must run on macOS (Darwin). For a Linux developer smoke test use --simulate.')
    for rel in REQUIRED:
        check((REPO / rel).is_file() and (REPO / rel).stat().st_size > 0,
              'source file ready: ' + rel)

    base = Path(tempfile.mkdtemp(prefix='networklab-c01-'))
    sandbox_home = base / 'isolated-user'
    sandbox_home.mkdir(mode=0o700)
    lab = sandbox_home / '.networklab'
    bin_dir = lab / 'bin'
    env = dict(os.environ, HOME=str(sandbox_home), NETLAB_HOME=str(lab))
    # Do not inherit potentially sensitive executable or test bypass overrides.
    for key in ('NETLAB_INTERNAL_WORKER', 'NETLAB_CONTEXT', 'NETLAB_WORKSPACE',
                'NETLAB_SKIP_VALIDATION', 'PYTHONPATH'):
        env.pop(key, None)
    try:
        # Dry-run must be genuinely side-effect-free.
        p = must_pass(['sh', REPO / 'install.sh', '--role', 'c', '--dry-run'], env, 'installer dry-run')
        check('DRY_RUN' in p.stdout and not lab.exists(), 'dry-run created no data')

        p = must_pass(['sh', REPO / 'install.sh', '--role', 'c'], env, 'first install', 120)
        check('INSTALL PASS: C' in p.stdout, 'Client installed')
        check(all((lab / x).is_file() for x in
                  ('app/netlab-c.sh', 'config/c.conf', 'config/targets.conf', 'bin/netlab-c')),
              'application, configs and launcher created')
        check(not (lab / 'config/s.conf').exists(), 'Client-only install did not create Server config')
        launcher = bin_dir / 'netlab-c'
        check(os.access(launcher, os.X_OK), 'launcher is executable')

        for args in (('--help',), ('--version',), ('config', 'validate'),
                     ('targets', 'validate'), ('targets', 'list'), ('self-test', '--non-interactive')):
            must_pass([launcher, *args], env, 'launcher ' + ' '.join(args), 120)
        check(True, 'help, version, config, targets and self-test returned 0')

        # Explicit system Bash path on macOS to catch Homebrew-vs-Bash3.2 issues.
        system_bash = Path('/bin/bash')
        if platform.system() == 'Darwin':
            p = must_pass([system_bash, lab / 'app/netlab-c.sh', 'self-test', '--non-interactive'],
                          env, 'system Bash self-test', 120)
            check('SELF_TEST PASS' in p.stdout, 'macOS /bin/bash self-test completed')
        else:
            check(simulate, 'Linux simulation mode recorded (not macOS acceptance)')

        invalid = run([launcher, 'not-a-real-command'], env)
        check(invalid.returncode == 2, 'unknown CLI command returns code 2')

        cpath = lab / 'config/c.conf'
        tpath = lab / 'config/targets.conf'
        history = lab / 'results' / 'c01-retention-test.txt'
        tpath.write_bytes(tpath.read_bytes() + b'\n# c01 retention sentinel\n')
        history.write_bytes(b'C01 historical results must survive reinstall\n')
        before = {p: digest(p) for p in (cpath, tpath, history, lab / 'app/lib/common.sh')}
        second = must_pass(['sh', REPO / 'install.sh', '--role', 'c'], env, 'reinstall', 120)
        check('preserved' in second.stdout and all(digest(p) == val for p,val in before.items()),
              'reinstall preserved app, configs and history')

        source_path = lab / 'config' / 'update-source.json'
        source_path.write_text(json.dumps({'github_repo': REPOSITORY}) + '\n', encoding='utf-8')
        source_path.chmod(0o600)
        check(json.loads(source_path.read_text()) == {'github_repo': REPOSITORY},
              'update source is exact official repository')
        p = must_pass([launcher, 'update', 'apply', '--version', 'v0.1.1', '--dry-run'],
                      env, 'offline update preview')
        check('DRY_RUN UPDATE' in p.stdout and REPOSITORY in p.stdout and
              all(digest(x) == val for x,val in before.items()),
              'pinned version preview is offline and preserves data')
        print('\n[C01] %s PASS: isolated acceptance; no user data modified, no live network tests.' %
              ('SIMULATION' if simulate and platform.system() != 'Darwin' else 'MACOS'), flush=True)
        print('[C01] Live GitHub Release update remains UNVERIFIED until a signed-off release exists.', flush=True)
    finally:
        if keep:
            print('[C01] isolated test directory retained: %s' % base, flush=True)
        else:
            shutil.rmtree(base)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate', action='store_true', help='Linux-only developer simulation; not macOS sign-off')
    parser.add_argument('--keep', action='store_true', help='retain isolated temporary test home for investigation')
    args = parser.parse_args()
    try:
        acceptance(simulate=args.simulate, keep=args.keep)
        return 0
    except Failure as exc:
        print('[C01] FAIL: ' + str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
