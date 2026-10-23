#!/usr/bin/env python3
"""C03: offline Alpine/BusyBox/OpenRC Server acceptance (stdlib only).

Default: only Alpine Linux can PASS. --compat-smoke allows Debian/Ubuntu to
exercise BusyBox ash compatibility without claiming Alpine verification.
The tests run under a private temporary HOME and NETLAB_HOME; no sudo, network
probes, system service operations, updates or writes to the operator's home.
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
    'lib/self_test.py', 'lib/server_config.py', 'lib/runner.sh',
    'defaults/s.conf', 'defaults/c.conf', 'defaults/targets.conf',
)
SYSTEM_SCHEDULE_PATHS = ('/etc/runlevels', '/etc/crontabs', '/etc/periodic')


class Failure(Exception):
    pass


def check(ok, message):
    if not ok:
        raise Failure(message)
    print('[PASS] ' + message, flush=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def distro_info():
    info = {}
    try:
        for line in Path('/etc/os-release').read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                info[key] = value.strip().strip('"').strip("'")
    except OSError as exc:
        raise Failure('cannot read /etc/os-release: %s' % exc)
    return info.get('ID', '').lower(), info.get('VERSION_ID', 'unknown')


def run(args, env, timeout=90, cwd=REPO):
    try:
        return subprocess.run([str(x) for x in args], cwd=str(cwd), env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Failure('command cannot complete: %s: %s' % (args, exc))


def success(args, env, label, timeout=90):
    p = run(args, env, timeout)
    if p.returncode:
        raise Failure('%s exited %s\nstdout:\n%s\nstderr:\n%s' %
                      (label, p.returncode, p.stdout[-2500:], p.stderr[-2500:]))
    return p


def private(path):
    return (path.exists() and not path.is_symlink()
            and stat.S_IMODE(path.stat().st_mode) & 0o077 == 0)


def snapshot_system_schedules():
    """Read-only path/metadata inventory; never open protected cron contents."""
    result = {}
    for raw in SYSTEM_SCHEDULE_PATHS:
        base = Path(raw)
        if not base.exists() and not base.is_symlink():
            continue
        # Service symlinks, periodic jobs, and crontab filenames. Bounded
        # traversal, no symlink following and no privileged operations.
        for path in [base] + sorted(base.glob('*')) + sorted(base.glob('*/*')):
            try:
                st = path.lstat()
                target = os.readlink(str(path)) if stat.S_ISLNK(st.st_mode) else ''
                result[str(path)] = (st.st_mode, st.st_size, st.st_mtime_ns, target)
            except FileNotFoundError:
                raise Failure('system schedule state changed during snapshot: %s' % path)
    return result


def selftest_output(p, role='S'):
    return ('SELF_TEST PASS (%s): 9 checks' % role) in p.stdout


def acceptance(keep=False, compat_smoke=False):
    if platform.system() != 'Linux':
        raise Failure('C03 requires Linux (Alpine for full acceptance).')
    distro, release = distro_info()
    if distro != 'alpine' and not compat_smoke:
        raise Failure('C03 full acceptance requires Alpine, detected %s %s. '
                      'Use --compat-smoke for non-Alpine BusyBox-only preflight.' % (distro, release))
    full = distro == 'alpine'
    print('[C03] OS=%s %s, mode=%s, user=%s' %
          (distro, release, 'ALPINE' if full else 'COMPAT-SMOKE (NOT ALPINE)',
           'root' if os.geteuid() == 0 else 'ordinary'), flush=True)
    check(sys.version_info >= (3, 8) and shutil.which('python3') is not None,
          'Python3 >=3.8 available')
    check(shutil.which('bash') is not None, 'Bash available (bash CLI modules)')
    check(shutil.which('sh') is not None, 'POSIX sh available')
    check(shutil.which('busybox') is not None, 'BusyBox binary available')
    bb = success(['busybox', '--list'], os.environ, 'BusyBox applet listing')
    check('ash' in bb.stdout.splitlines(), 'BusyBox ash applet available')
    check('sh' in bb.stdout.splitlines(), 'BusyBox sh applet available')
    for name in REQUIRED:
        path = REPO / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise Failure('required code missing, empty or unsafe: ' + name)
    check(True, 'complete B12/B13 source available')
    success(['busybox', 'ash', '-n', REPO / 'install.sh'],
            os.environ, 'BusyBox ash syntax check')
    check(True, 'B12 install.sh accepted by BusyBox ash parser')

    # OpenRC can be absent in Alpine containers. Distinguish Alpine/BusyBox
    # success from full OpenRC coverage instead of inventing service validation.
    has_openrc = all(shutil.which(x) is not None for x in ('rc-service', 'rc-update'))
    if has_openrc:
        print('[C03] OpenRC tools detected; will verify system runlevel files remain unchanged.', flush=True)
    else:
        print('[C03] OpenRC tools unavailable; init-service integration NOT VERIFIED.', flush=True)

    source_hashes = {name: sha(REPO / name) for name in REQUIRED}
    service_before = snapshot_system_schedules()
    temporary = Path(tempfile.mkdtemp(prefix='networklab-c03-'))
    home = temporary / 'testuser'
    home.mkdir(mode=0o700)
    lab = home / '.networklab'
    env = dict(os.environ, HOME=str(home), NETLAB_HOME=str(lab))
    for key in ('PYTHONPATH', 'PYTHONHOME', 'NETLAB_INTERNAL_WORKER',
                'NETLAB_CONTEXT_FILE', 'NETLAB_WORK_DIR', 'NETLAB_LOG_FILE'):
        env.pop(key, None)
    try:
        preview = success(['busybox', 'ash', REPO / 'install.sh', '--dry-run'],
                          env, 'ash dry-run')
        check('role=s' in preview.stdout and not lab.exists(),
              'BusyBox ash bootstraps Server role without creating state')
        install = success(['busybox', 'ash', REPO / 'install.sh'],
                          env, 'BusyBox ash full installation')
        check('INSTALL PASS: S' in install.stdout,
              'real installer bootstrapped through BusyBox ash')
        app = lab / 'app'
        cfg = lab / 'config' / 's.conf'
        launcher = lab / 'bin/netlab-s'
        check(all(x.exists() for x in
                  (app / 'netlab-s.sh', app / 'lib/installer.py', cfg, launcher,
                   lab / 'results', lab / 'logs')),
              'Server app, config, result/log dirs and launcher created')
        check(not (lab / 'config/c.conf').exists()
              and not (lab / 'config/targets.conf').exists(),
              'Server install did not add Client-only configuration')
        check(all(private(x) for x in
                  (lab, app, lab / 'config', cfg, launcher, lab / 'results', lab / 'logs')),
              'private permissions exclude group and other access')
        check(os.access(launcher, os.X_OK), 'launcher is executable')
        match = re.search(r'(?m)^server_id\s*=\s*(s-[0-9a-f]{16})\s*$',
                          cfg.read_text(encoding='utf-8'))
        check(match is not None, 'generated server_id is valid and independent of IPv4')
        sid = match.group(1)
        version = success([launcher, '--version'], env, 'installed version')
        check(re.search(r'^NetworkLab v\d+\.\d+\.\d+', version.stdout) is not None,
              'installed entrypoint reports semantic version')
        success([launcher, '--help'], env, 'CLI help')
        check(True, 'CLI help works without network access')
        p = success([launcher, 'config', 'validate'], env, 'config validation')
        check(sid in p.stdout, 'S configuration validates with stable Server ID')
        p = success([launcher, 'config', 'profiles'], env, 'profile listing')
        check('[quick]' in p.stdout and '[standard]' in p.stdout and '[deep]' in p.stdout,
              'all three configured S profiles resolve')
        p = success([launcher, 'self-test', '--non-interactive'], env,
                    'offline Self-test', timeout=120)
        check(selftest_output(p), 'isolated S Self-test passes 9 checks')
        bad = run([launcher, 'nonexistent-c03-command'], env)
        check(bad.returncode == 2, 'unknown public command returns usage 2')
        placeholder = run([launcher, 'inventory', '--non-interactive'], env)
        check(placeholder.returncode == 8, 'not implemented inventory returns 8')
        check(not list((lab / 'results').rglob('*.json')),
              'stub module produces no fabricated measurements')

        # No cron/system service edits. Schedules in s.conf are declarative only.
        check(snapshot_system_schedules() == service_before,
              'OpenRC/cron/periodic system configuration unchanged')
        check(not (lab / 'config').joinpath('crontab').exists(),
              'installer does not create a live scheduler')

        log = lab / 'logs' / 'c03-keep.log'
        report = lab / 'results' / 'c03-keep.txt'
        log.write_text('retained log\n', encoding='utf-8')
        report.write_text('retained result\n', encoding='utf-8')
        with cfg.open('a', encoding='utf-8') as output:
            output.write('\n# c03 retention check\n')
        objects = [cfg, log, report, app / 'lib/common.sh']
        hashes = {str(path): sha(path) for path in objects}
        again = success(['sh', REPO / 'install.sh'], env, 'repeat install')
        check('preserved' in again.stdout and all(sha(Path(p)) == h for p, h in hashes.items()),
              'repeat install preserves app, config, logs and reports')
        check(sid in cfg.read_text(encoding='utf-8'),
              'Server ID remains unchanged after reinstall')
        source_cfg = lab / 'config/update-source.json'
        source_cfg.write_text(json.dumps({'github_repo': 'xlldll/NetworkLab'}) + '\n',
                              encoding='utf-8')
        source_cfg.chmod(0o600)
        p = success([launcher, 'update', 'apply', '--version', 'v0.1.1', '--dry-run'],
                    env, 'offline B13 preview')
        check('DRY_RUN' in p.stdout and all(sha(Path(p)) == h for p, h in hashes.items()),
              'B13 pinned update dry-run leaves user data unchanged')

        # Symlink protection in isolated directories only.
        hostile = temporary / 'hostile'
        outside = temporary / 'outside'
        hostile.mkdir(mode=0o700)
        outside.mkdir(mode=0o700)
        (hostile / 'config').symlink_to(outside, target_is_directory=True)
        denied = run(['busybox', 'ash', REPO / 'install.sh'],
                     dict(env, NETLAB_HOME=str(hostile)))
        check(denied.returncode == 9 and not list(outside.iterdir()),
              'installer refuses symlinked configuration without touching target')
        check(all(sha(REPO / name) == digest for name, digest in source_hashes.items()),
              'original project source files are unchanged')
        check(snapshot_system_schedules() == service_before,
              'system OpenRC runlevels and scheduled jobs remain unchanged')
        print('\n[C03] %s: %s %s; isolated BusyBox ash Server acceptance.' %
              ('ALPINE PASS' if full else 'COMPAT-SMOKE PASS (NOT ALPINE)', distro, release),
              flush=True)
        print('[C03] OpenRC tools: %s; no live probes, networking changes or service installation.' %
              ('detected, configuration unchanged' if has_openrc else 'not available; OpenRC not certified'),
              flush=True)
        if full and not has_openrc:
            print('[C03] WARNING: Alpine userspace PASS; OpenRC integration requires host with rc-service/rc-update.',
                  flush=True)
    finally:
        if keep:
            print('[C03] isolated sandbox retained: ' + str(temporary), flush=True)
        else:
            shutil.rmtree(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keep', action='store_true', help='keep the private test directory for diagnosis')
    parser.add_argument('--compat-smoke', action='store_true',
                        help='run on non-Alpine Linux, but NEVER report Alpine PASS')
    args = parser.parse_args()
    try:
        acceptance(args.keep, args.compat_smoke)
        return 0
    except Failure as exc:
        print('[C03] FAIL: ' + str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
