#!/usr/bin/env python3
"""NetworkLab B13 pinned GitHub Release updater (Python stdlib only).

Never sources user config or executes downloaded code before archive/hash checks.
Existing app/ is replaced only during an explicit update apply. Inactive apps only.
"""
import argparse
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import uuid
import zipfile

EXIT_USAGE, EXIT_CONFIG, EXIT_FAILED, EXIT_SAFETY, EXIT_BUSY = 2, 3, 5, 9, 10
SEMVER = re.compile(r'^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([A-Za-z0-9][A-Za-z0-9.-]*))?$')
REPO = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
SHA = re.compile(r'^[a-fA-F0-9]{64}$')
MAX_JSON, MAX_CHECKSUM, MAX_ZIP, MAX_UNPACK, MAX_MEMBERS = 1048576, 8192, 64 * 1024**2, 256 * 1024**2, 2000
FILE_REQ = ('install.sh', 'netlab-c.sh', 'netlab-s.sh', 'lib/common.sh', 'lib/runner.sh', 'lib/installer.py', 'lib/updater.py', 'defaults/c.conf', 'defaults/targets.conf', 'defaults/s.conf')

class UpdateError(Exception):
    def __init__(self, message, code=EXIT_FAILED):
        super().__init__(message)
        self.code = code


def no_duplicate_keys(pairs):
    result = {}
    for key, val in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: %s' % key)
        result[key] = val
    return result


def abs_path(value):
    if not value or not Path(value).is_absolute():
        raise UpdateError('NETLAB_HOME must be an absolute path', EXIT_CONFIG)
    path = Path(os.path.abspath(value))
    # macOS /var -> /private/var is a root-maintained system alias.
    cur = Path(path.anchor)
    for part in path.parts[1:]:
        cur /= part
        if cur.is_symlink():
            parent = cur.parent.stat()
            allowed = (str(cur) in ('/var', '/tmp') and parent.st_uid == 0 and not parent.st_mode & 0o022)
            if not allowed:
                raise UpdateError('unsafe symlink path: %s' % cur, EXIT_SAFETY)
    return path


def require_regular(path):
    if path.is_symlink() or not path.is_file():
        raise UpdateError('missing or unsafe file: %s' % path, EXIT_SAFETY)


def version(text):
    match = SEMVER.fullmatch(text)
    if not match:
        raise UpdateError('invalid release version: %s' % text, EXIT_USAGE)
    return 'v' + text.lstrip('v')


def semver_tuple(text):
    match = SEMVER.fullmatch(version(text))
    nums = tuple(int(x) for x in match.groups()[:3])
    suffix = match.group(4)
    # Pre-release is always lower than stable for the same core version.
    return (nums, (0, tuple((0, int(x)) if x.isdigit() else (1, x) for x in suffix.split('.'))) if suffix else (1, ()))


def app_version(app):
    value = app / 'lib/common.sh'
    require_regular(value)
    data = value.read_text(encoding='utf-8')
    match = re.search(r"(?m)^NETLAB_VERSION='([^']+)'$", data)
    if not match:
        raise UpdateError('installed app version missing', EXIT_CONFIG)
    return version(match.group(1))


def get_home():
    value = os.environ.get('NETLAB_HOME')
    if value is None:
        if not os.environ.get('HOME'):
            raise UpdateError('HOME is required', EXIT_CONFIG)
        value = str(Path(os.environ['HOME']) / '.networklab')
    return abs_path(value)


def read_repo_config(home):
    path = home / 'config/update-source.json'
    abs_path(str(path.parent))
    if not path.exists():
        raise UpdateError('update source not configured: create %s with {"github_repo":"OWNER/NetworkLab"}' % path, EXIT_CONFIG)
    require_regular(path)
    if path.stat().st_size > 4096:
        raise UpdateError('update source config too large', EXIT_CONFIG)
    try:
        data = json.loads(path.read_text('utf-8'), object_pairs_hook=no_duplicate_keys)
    except (UnicodeError, ValueError) as exc:
        raise UpdateError('invalid update source: %s' % exc, EXIT_CONFIG)
    if not isinstance(data, dict) or set(data) != {'github_repo'} or not isinstance(data['github_repo'], str) or not REPO.fullmatch(data['github_repo']) or '..' in data['github_repo'].split('/'):
        raise UpdateError('update source must contain only valid github_repo OWNER/REPO', EXIT_CONFIG)
    return data['github_repo']


def url_bytes(url, max_bytes):
    if urlparse(url).scheme != 'https':
        raise UpdateError('HTTPS required for release download', EXIT_SAFETY)
    req = Request(url, headers={'User-Agent': 'NetworkLab-B13/0.1', 'Accept': 'application/vnd.github+json'})
    try:
        with urlopen(req, timeout=20) as res:
            final = urlparse(res.geturl())
            allowed_hosts = ('api.github.com', 'github.com',
                             'objects.githubusercontent.com', 'release-assets.githubusercontent.com')
            if final.scheme != 'https' or final.hostname not in allowed_hosts:
                raise UpdateError('untrusted Release redirect', EXIT_SAFETY)
            out = res.read(max_bytes + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise UpdateError('remote request failed: %s' % exc)
    if len(out) > max_bytes:
        raise UpdateError('remote file exceeds size limit', EXIT_SAFETY)
    return out


def release_metadata(repo, tag=None):
    endpoint = ('latest' if tag is None else 'tags/' + quote(tag, safe=''))
    url = 'https://api.github.com/repos/%s/releases/%s' % (repo, endpoint)
    try:
        obj = json.loads(url_bytes(url, MAX_JSON).decode('utf-8'), object_pairs_hook=no_duplicate_keys)
    except (UnicodeError, ValueError) as exc:
        raise UpdateError('invalid GitHub Release JSON: %s' % exc)
    if not isinstance(obj, dict):
        raise UpdateError('invalid GitHub Release response')
    if not isinstance(obj.get('tag_name'), str):
        raise UpdateError('GitHub Release missing valid tag_name')
    actual = version(obj['tag_name'])
    if tag and actual != version(tag):
        raise UpdateError('GitHub Release tag mismatch', EXIT_SAFETY)
    if obj.get('draft') or obj.get('prerelease'):
        raise UpdateError('draft/prerelease is not eligible for B13 stable updates', EXIT_SAFETY)
    return obj


def release_asset_urls(repo, metadata, tag):
    archive = 'networklab-%s.zip' % tag
    checksum = archive + '.sha256'
    results = {}
    assets = metadata.get('assets')
    if not isinstance(assets, list):
        raise UpdateError('GitHub Release assets must be a list')
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get('name')
        if name not in (archive, checksum):
            continue
        if name in results:
            raise UpdateError('duplicate Release asset: %s' % name, EXIT_SAFETY)
        url = asset.get('browser_download_url', '')
        expected = 'https://github.com/%s/releases/download/%s/%s' % (repo, quote(tag, safe=''), name)
        if url != expected:
            raise UpdateError('asset URL does not match trusted GitHub repo/tag', EXIT_SAFETY)
        results[name] = url
    if archive not in results or checksum not in results:
        raise UpdateError('Release needs both %s and its SHA256 sidecar' % archive)
    return results[archive], results[checksum]


def get_expected_digest(content, name):
    try:
        line = content.decode('ascii').strip()
    except UnicodeError:
        raise UpdateError('checksum file is not ASCII', EXIT_SAFETY)
    fields = line.split()
    if len(fields) not in (1, 2) or not SHA.fullmatch(fields[0]):
        raise UpdateError('invalid SHA-256 sidecar', EXIT_SAFETY)
    if len(fields) == 2 and fields[1].lstrip('*') != name:
        raise UpdateError('checksum filename mismatch', EXIT_SAFETY)
    return fields[0].lower()


def unpack_verified_archive(data, dest):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except (OSError, zipfile.BadZipFile) as exc:
        raise UpdateError('invalid Release ZIP: %s' % exc, EXIT_SAFETY)
    with z:
        infos = z.infolist()
        if len(infos) > MAX_MEMBERS or sum(f.file_size for f in infos) > MAX_UNPACK:
            raise UpdateError('Release ZIP too large', EXIT_SAFETY)
        names = [f.filename for f in infos if f.filename and not f.is_dir()]
        if not names:
            raise UpdateError('empty Release ZIP', EXIT_SAFETY)
        # Support a single top-level GitHub-style wrapping folder, or flat archive.
        parts = [PurePosixPath(name).parts for name in names]
        prefix = parts[0][0] if len(parts[0]) > 1 and all(p[0] == parts[0][0] and len(p) > 1 for p in parts) and parts[0][0] not in ('lib', 'defaults', 'c', 's', 'docs', 'tests', 'schemas', 'examples') else None
        seen = set()
        for info in infos:
            raw = info.filename
            if '\\' in raw or '\x00' in raw or raw.startswith('/') or ':' in raw:
                raise UpdateError('unsafe ZIP member: %s' % raw, EXIT_SAFETY)
            p = PurePosixPath(raw)
            if any(x in ('.', '..', '') for x in raw.rstrip('/').split('/')):
                raise UpdateError('path traversal in ZIP: %s' % raw, EXIT_SAFETY)
            if prefix:
                if p.parts[0] != prefix:
                    raise UpdateError('inconsistent ZIP wrapper', EXIT_SAFETY)
                p = PurePosixPath(*p.parts[1:])
                if str(p) == '.':
                    continue
            key = str(p).casefold()
            if key in seen:
                raise UpdateError('duplicate ZIP member: %s' % p, EXIT_SAFETY)
            seen.add(key)
            mode = (info.external_attr >> 16)
            ftype = stat.S_IFMT(mode)
            if ftype not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise UpdateError('ZIP contains a link or special file: %s' % p, EXIT_SAFETY)
            target = dest.joinpath(*p.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                os.chmod(target, 0o700)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info, 'r') as src, open(target, 'xb') as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                os.chmod(target, 0o700 if p.name.endswith('.sh') else 0o600)
    for name in FILE_REQ:
        require_regular(dest / name)
    for path in dest.rglob('*'):
        if path.is_symlink():
            raise UpdateError('archive created a symbolic link', EXIT_SAFETY)


def check_new_app(app, home):
    roles = []
    if (home / 'config/c.conf').exists():
        roles.append('c')
    if (home / 'config/s.conf').exists():
        roles.append('s')
    if not roles:
        raise UpdateError('no installed C/S configuration available', EXIT_CONFIG)
    env = dict(os.environ, NETLAB_HOME=str(home))
    for role in roles:
        cmds = [['bash', str(app / ('netlab-%s.sh' % role)), 'config', 'validate'],
                ['bash', str(app / ('netlab-%s.sh' % role)), 'self-test', '--quiet', '--non-interactive']]
        if role == 'c':
            cmds.insert(1, ['bash', str(app / 'netlab-c.sh'), 'targets', 'validate'])
        for cmd in cmds:
            try:
                r = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise UpdateError('post-update validation crashed: %s' % exc)
            if r.returncode:
                raise UpdateError('post-update validation failed (%s): %s' % (role, r.stderr.decode('utf-8', 'replace')[-500:]))


def apply_update(home, root, repo, tag, quiet=False):
    app = home / 'app'
    if not app.is_dir() or app.is_symlink():
        raise UpdateError('installed app missing or unsafe', EXIT_CONFIG)
    lock_path = home / '.install.lock'
    if lock_path.is_symlink():
        raise UpdateError('unsafe install/update lock', EXIT_SAFETY)
    with open(lock_path, 'a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Check all paths again inside lock.
        abs_path(str(home))
        current = app_version(app)
        if current == tag:
            if not quiet: print('[NetworkLab] already installed:', tag)
            return 0
        if semver_tuple(tag) < semver_tuple(current):
            raise UpdateError('downgrade not supported: %s -> %s' % (current, tag), EXIT_CONFIG)
        meta = release_metadata(repo, tag)
        archive_url, sum_url = release_asset_urls(repo, meta, tag)
        archive_name = 'networklab-%s.zip' % tag
        wanted = get_expected_digest(url_bytes(sum_url, MAX_CHECKSUM), archive_name)
        data = url_bytes(archive_url, MAX_ZIP)
        if hashlib.sha256(data).hexdigest() != wanted:
            raise UpdateError('Release ZIP SHA-256 mismatch', EXIT_SAFETY)
        stage = Path(tempfile.mkdtemp(prefix='.netlab-upgrade-stage-', dir=str(home)))
        backup = home / ('.netlab-upgrade-backup-' + uuid.uuid4().hex)
        bad = home / ('.netlab-upgrade-failed-' + uuid.uuid4().hex)
        moved_old = moved_new = False
        try:
            unpack_verified_archive(data, stage)
            if app_version(stage) != tag:
                raise UpdateError('archive source NETLAB_VERSION does not match Release tag', EXIT_SAFETY)
            # Validate before touching existing app, then validate again after cutover.
            check_new_app(stage, home)
            os.rename(app, backup)
            moved_old = True
            try:
                os.rename(stage, app)
                moved_new = True
                check_new_app(app, home)
            except Exception:
                if moved_new and app.exists():
                    os.rename(app, bad)
                os.rename(backup, app)
                moved_old = False
                raise
            shutil.rmtree(backup)
            moved_old = False
            if not quiet:
                print('[NetworkLab] UPDATE PASS: %s -> %s' % (current, tag))
            return 0
        finally:
            if moved_old and backup.exists() and not app.exists():
                os.rename(backup, app)
            if stage.exists():
                shutil.rmtree(stage)
            if bad.exists():
                shutil.rmtree(bad)


def main(argv=None):
    parser = argparse.ArgumentParser(description='NetworkLab pinned GitHub Release updater')
    parser.add_argument('--root', required=True)
    parser.add_argument('--role', required=True, choices=('c', 's'))
    parser.add_argument('--action', required=True, choices=('check', 'apply'))
    parser.add_argument('--version')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        home = get_home()
        root = abs_path(args.root)
        app = home / 'app'
        if not app.is_dir() or app.is_symlink():
            raise UpdateError('installed app missing (run sh install.sh first)', EXIT_CONFIG)
        require_regular(root / 'lib/updater.py')
        current = app_version(app)
        repo = read_repo_config(home)
        if args.action == 'check':
            meta = release_metadata(repo)
            latest = version(meta.get('tag_name', ''))
            release_asset_urls(repo, meta, latest)  # Require deployable assets, not just a Tag.
            newer = semver_tuple(latest) > semver_tuple(current)
            if not args.quiet:
                print('[NetworkLab] UPDATE_CHECK installed=%s latest=%s available=%s repo=%s' % (current, latest, str(newer).lower(), repo))
            return 0
        if not args.version:
            raise UpdateError('update apply requires --version', EXIT_USAGE)
        tag = version(args.version)
        if args.dry_run:
            print('[NetworkLab] DRY_RUN UPDATE: %s -> %s via GitHub Releases %s (no network or changes)' % (current, tag, repo))
            return 0
        return apply_update(home, root, repo, tag, quiet=args.quiet)
    except BlockingIOError:
        print('[NetworkLab] UPDATE_BUSY (10): another install or update is active', file=sys.stderr)
        return EXIT_BUSY
    except UpdateError as exc:
        print('[NetworkLab] UPDATE_ERROR (%s): %s' % (exc.code, exc), file=sys.stderr)
        return exc.code
    except (OSError, ValueError, UnicodeError, RuntimeError) as exc:
        print('[NetworkLab] UPDATE_ERROR (5): %s' % exc, file=sys.stderr)
        return EXIT_FAILED


if __name__ == '__main__':
    sys.exit(main())
