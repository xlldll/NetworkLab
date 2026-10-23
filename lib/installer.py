#!/usr/bin/env python3
"""NetworkLab B12 offline, user-scoped install manager (stdlib only).

B12 does NOT update an existing installed app; B13 owns upgrades/rollback.
No remote requests, chmod of existing user files, root escalation, or cron.
"""

import argparse
import contextlib
import fcntl
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile

EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_DEP = 4
EXIT_FAILED = 5
EXIT_SAFETY = 9
ROLE_ENTRIES = {'c': 'netlab-c.sh', 's': 'netlab-s.sh'}
REQUIRED_DIRS = ('c', 's', 'lib', 'defaults', 'schemas', 'docs', 'tests')
OPTIONAL_DIRS = ('examples',)
REQUIRED_FILES = ('netlab-c.sh', 'netlab-s.sh', 'install.sh')
OPTIONAL_FILES = ('README.md', 'LICENSE', 'THIRD_PARTY_LICENSES.md')
MARKER = '# NetworkLab B12 managed launcher; do not edit'


class InstallError(Exception):
    def __init__(self, message, code=EXIT_FAILED):
        super().__init__(message)
        self.code = code


def reject_symlink_parts(path):
    """Reject symlink components (including dangling links) in install paths."""
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            # macOS exposes /var and /tmp as root-maintained links into
            # /private. Accept only symlinks in a root-owned, non-writable
            # parent; never trust a link inside a user-writable directory.
            parent = current.parent.stat()
            managed_by_root = (str(current) in ('/var', '/tmp')
                               and parent.st_uid == 0
                               and not (parent.st_mode & 0o022))
            if not managed_by_root:
                raise InstallError('refusing symlink path: %s' % current, EXIT_SAFETY)


def absolute_path(value, label):
    path = Path(value)
    if not path.is_absolute() or '\x00' in value:
        raise InstallError('%s must be absolute' % label, EXIT_CONFIG)
    # Resolve dot/dotdot lexically only; do not follow links before safety check.
    path = Path(os.path.abspath(value))
    reject_symlink_parts(path)
    return path


def ensure_directory(path):
    reject_symlink_parts(path)
    if path.exists():
        if not path.is_dir():
            raise InstallError('not a directory: %s' % path, EXIT_SAFETY)
        return False
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    reject_symlink_parts(path)
    return True


def ensure_regular(path):
    if path.is_symlink():
        raise InstallError('refusing symlink file: %s' % path, EXIT_SAFETY)
    if path.exists() and not path.is_file():
        raise InstallError('not a regular file: %s' % path, EXIT_SAFETY)


def require_safe_sources(root):
    for name in REQUIRED_DIRS:
        base = root / name
        if base.is_symlink() or not base.is_dir():
            raise InstallError('source directory missing or unsafe: %s' % base)
    for name in REQUIRED_FILES:
        base = root / name
        if base.is_symlink() or not base.is_file():
            raise InstallError('source file missing or unsafe: %s' % base)
    for name in ('lib/installer.py', 'lib/common.sh', 'lib/runner.sh',
                 'lib/config_manager.py', 'lib/server_config.py',
                 'lib/updater.py',
                 'defaults/c.conf', 'defaults/targets.conf', 'defaults/s.conf'):
        file = root / name
        if file.is_symlink() or not file.is_file():
            raise InstallError('missing application dependency: %s' % name)
    for folder in REQUIRED_DIRS + OPTIONAL_DIRS:
        base = root / folder
        if not base.exists():
            continue
        for dirname, dirs, files in os.walk(base, followlinks=False):
            for name in dirs + files:
                member = Path(dirname) / name
                if member.is_symlink():
                    raise InstallError('source contains symlink: %s' % member, EXIT_SAFETY)
                if member.is_file() and not member.is_symlink():
                    continue
                if member.is_dir() and not member.is_symlink():
                    continue
                raise InstallError('source contains special file: %s' % member, EXIT_SAFETY)


def select_home():
    if 'NETLAB_HOME' in os.environ:
        text = os.environ['NETLAB_HOME']
        if not text:
            raise InstallError('NETLAB_HOME cannot be empty', EXIT_CONFIG)
        return absolute_path(text, 'NETLAB_HOME'), True
    home = os.environ.get('HOME', '')
    if not home:
        raise InstallError('HOME is required', EXIT_CONFIG)
    return absolute_path(str(Path(home) / '.networklab'), 'NETLAB_HOME'), False


def choose_bin_dir(home, explicit, custom_home):
    if explicit:
        return absolute_path(explicit, '--bin-dir')
    if custom_home:
        return absolute_path(str(home / 'bin'), 'binary directory')
    return absolute_path(str(Path(os.environ['HOME']) / '.local' / 'bin'), 'binary directory')


def launcher_text(home, role):
    # repr() is Python quoting, not POSIX sh quoting; use explicit safe POSIX quoting.
    quoted = "'" + str(home).replace("'", "'\\''") + "'"
    return ('#!/bin/sh\n' + MARKER + '\n'
            + 'NETLAB_INSTALLED_HOME=' + quoted + '\n'
            + 'exec bash "$NETLAB_INSTALLED_HOME/app/netlab-' + role + '.sh" "$@"\n')


def write_atomic_if_missing(target, data, mode=0o600, managed=False):
    ensure_regular(target)
    if target.exists():
        if managed:
            existing = target.read_bytes()
            if existing != data:
                raise InstallError('command name already exists with different content: %s' % target,
                                   EXIT_SAFETY)
        return False
    handle, tmpname = tempfile.mkstemp(prefix='.' + target.name + '.install-', dir=str(target.parent))
    try:
        with os.fdopen(handle, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmpname, mode)
        # Under installer lock, and refuse unexpected files rather than overwrite.
        if target.exists() or target.is_symlink():
            raise InstallError('destination appeared during initialization: %s' % target, EXIT_SAFETY)
        os.link(tmpname, target)  # O_EXCL-like creation; never replace existing data.
        return True
    finally:
        try:
            os.unlink(tmpname)
        except FileNotFoundError:
            pass


def install_app(source, app):
    ensure_regular(app) if app.exists() and not app.is_dir() else None
    if app.exists():
        if not app.is_dir() or app.is_symlink():
            raise InstallError('unsafe existing app directory: %s' % app, EXIT_SAFETY)
        for name in REQUIRED_FILES + ('lib/installer.py',):
            file = app / name
            if file.is_symlink() or not file.is_file():
                raise InstallError('existing app incomplete: %s (B13 should handle upgrades)' % file)
        return False
    stage = Path(tempfile.mkdtemp(prefix='.app-stage-', dir=str(app.parent)))
    try:
        for name in REQUIRED_DIRS + OPTIONAL_DIRS:
            src = source / name
            if src.exists():
                shutil.copytree(src, stage / name, symlinks=False)
        for name in REQUIRED_FILES + OPTIONAL_FILES:
            src = source / name
            if src.exists():
                if src.is_symlink() or not src.is_file():
                    raise InstallError('unsafe source file: %s' % src, EXIT_SAFETY)
                shutil.copy2(src, stage / name)
        # All files in app are owned by the user, not world writable.
        for dirname, dirs, files in os.walk(stage):
            os.chmod(dirname, 0o700)
            for name in files:
                file = Path(dirname) / name
                original_mode = stat.S_IMODE(file.stat().st_mode)
                os.chmod(file, 0o700 if original_mode & 0o111 else 0o600)
        if app.exists() or app.is_symlink():
            raise InstallError('app appeared during installation: %s' % app, EXIT_SAFETY)
        os.rename(stage, app)
        return True
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def init_config(home, app, role):
    config = home / 'config'
    files = ('c.conf', 'targets.conf') if role == 'c' else ('s.conf',)
    created = []
    server_id = None
    for name in files:
        dest = config / name
        source_text = (app / 'defaults' / name).read_bytes()
        if name == 's.conf' and not dest.exists():
            server_id = 's-' + secrets.token_hex(8)
            raw = source_text.decode('utf-8')
            needle = 'server_id = CHANGE_ME'
            if raw.count(needle) != 1:
                raise InstallError('s.conf template missing unique server_id placeholder')
            source_text = raw.replace(needle, 'server_id = ' + server_id).encode('utf-8')
        if write_atomic_if_missing(dest, source_text):
            created.append(name)
    return created, server_id


def validate_installed(home, app, role, run_self_test):
    env = os.environ.copy()
    env['NETLAB_HOME'] = str(home)
    entry = app / ROLE_ENTRIES[role]
    commands = [["bash", str(entry), 'config', 'validate']]
    if role == 'c':
        commands.append(["bash", str(entry), 'targets', 'validate'])
    if run_self_test:
        commands.append(["bash", str(entry), 'self-test', '--non-interactive', '--quiet'])
    for argv in commands:
        try:
            p = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InstallError('post-install verification error: %s' % exc)
        if p.returncode:
            raise InstallError('post-install validation returned %s for %s\n%s' %
                               (p.returncode, argv[2], (p.stderr or p.stdout).strip()),
                               EXIT_CONFIG if argv[2] == 'config' else EXIT_FAILED)
        print(p.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description='NetworkLab B12 offline install manager')
    parser.add_argument('--source', required=True)
    parser.add_argument('--role', choices=('c', 's'), required=True)
    parser.add_argument('--platform', required=True)
    parser.add_argument('--arch', required=True)
    parser.add_argument('--bin-dir', default='')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--skip-self-test', action='store_true')
    args = parser.parse_args()
    try:
        source = absolute_path(args.source, 'source path')
        require_safe_sources(source)
        home, overridden = select_home()
        bindir = choose_bin_dir(home, args.bin_dir, overridden)
        app, config = home / 'app', home / 'config'
        dest = bindir / ('netlab-' + args.role)
        data = launcher_text(home, args.role).encode('utf-8')
        # A command already owned by another application must never be replaced.
        for path in (home, app, config, home / 'results', home / 'logs', bindir, dest):
            reject_symlink_parts(path)
        ensure_regular(dest)
        if dest.exists():
            if dest.read_bytes() != data:
                raise InstallError('refusing to overwrite existing command: %s' % dest, EXIT_SAFETY)
            if not os.access(dest, os.X_OK):
                raise InstallError('existing command is not executable: %s' % dest, EXIT_SAFETY)
        if args.dry_run:
            print('[NetworkLab] DRY_RUN B12: platform=%s arch=%s role=%s' %
                  (args.platform, args.arch, args.role))
            print('[NetworkLab] DRY_RUN app=%s (copy only if absent)' % app)
            print('[NetworkLab] DRY_RUN config=%s (preserve existing files)' % config)
            print('[NetworkLab] DRY_RUN command=%s (no PATH changes)' % dest)
            return 0
        old_umask = os.umask(0o077)
        try:
            ensure_directory(home)
            lock_path = home / '.install.lock'
            ensure_regular(lock_path)
            with open(lock_path, 'a+b') as lock:
                os.chmod(lock_path, 0o600)
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                for directory in (config, home / 'results', home / 'logs', bindir):
                    ensure_directory(directory)
                fresh_app = install_app(source, app)
                created, sid = init_config(home, app, args.role)
                write_atomic_if_missing(dest, data, mode=0o700, managed=True)
                validate_installed(home, app, args.role, not args.skip_self_test)
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        finally:
            os.umask(old_umask)
        print('[NetworkLab] INSTALL PASS: %s (%s/%s)' % (args.role.upper(), args.platform, args.arch))
        print('[NetworkLab] app: %s [%s]' % (app, 'created' if fresh_app else 'preserved'))
        print('[NetworkLab] config created: %s' % (', '.join(created) if created else '(none; preserved)'))
        if sid:
            print('[NetworkLab] generated server_id: %s' % sid)
        print('[NetworkLab] command: %s' % dest)
        if str(bindir) not in os.environ.get('PATH', '').split(os.pathsep):
            print('[NetworkLab] PATH NOTICE: add this directory to PATH if desired: %s' % bindir)
        print('[NetworkLab] v0.1.0: no live probes, timers, services or remote updates were run')
        return 0
    except InstallError as exc:
        print('[NetworkLab] %s (%d): %s' % (
            'SAFETY_BLOCKED' if exc.code == EXIT_SAFETY else 'INSTALL_ERROR', exc.code, exc), file=sys.stderr)
        return exc.code
    except (OSError, UnicodeError, ValueError) as exc:
        print('[NetworkLab] INSTALL_ERROR (5): %s' % exc, file=sys.stderr)
        return EXIT_FAILED


if __name__ == '__main__':
    sys.exit(main())
