#!/usr/bin/env python3
"""C07: read-only NetworkLab source and Release-asset audit (Python >= 3.8).

Default mode is offline and makes no network requests. Pass --asset/--checksum
and --tag to verify locally staged GitHub Release artifacts. With --online,
check an explicitly pinned GitHub Release using the updater's guarded transport.
No probes, installations, Git mutations, or writes outside temporary storage.
"""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

VERSION_RE = re.compile(r"(?m)^NETLAB_VERSION='(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([A-Za-z0-9][A-Za-z0-9.-]*))?'$")
TAG_RE = re.compile(r'^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([A-Za-z0-9][A-Za-z0-9.-]*))?$')
SHA_RE = re.compile(r'^[0-9a-fA-F]{64}$')
REQUIRED = (
    'README.md', 'LICENSE', 'install.sh', 'netlab-c.sh', 'netlab-s.sh',
    'lib/common.sh', 'lib/cli.sh', 'lib/runner.sh', 'lib/installer.py',
    'lib/updater.py', 'lib/report.py', 'lib/result_browser.py', 'lib/s_inventory.py', 'lib/c_inventory.py', 'lib/c_tcp_connect.py',
    'scripts/release_audit.py', 'tests/test-c07-all.sh',
    'docs/implementation-c07.md', '.github/workflows/ci.yml',
    'defaults/c.conf', 'defaults/targets.conf', 'defaults/s.conf',
)
WORKERS = (
    'c/c-inventory.sh', 'c/c-standalone.sh', 'c/c-paired.sh',
    'c/c-proxy.sh', 'c/c-collect.sh', 's/s-inventory.sh',
    's/s-toolbox.sh', 's/s-service.sh', 's/s-scheduler.sh',
)
IMPLEMENTED_WORKERS = ('s/s-inventory.sh', 'c/c-inventory.sh', 'c/c-standalone.sh')  # D01-D03
MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_UNPACK_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 2000
MAX_README = 64 * 1024


class AuditError(Exception):
    pass


def check(condition, message):
    if not condition:
        raise AuditError(message)


def get_version(raw):
    match = VERSION_RE.search(raw)
    check(match is not None, 'missing or invalid NETLAB_VERSION in lib/common.sh')
    return match.group(0).split("'")[1]


def validate_readme(raw, version=None):
    check(100 <= len(raw) <= MAX_README, 'README missing or wrong size')
    required = ('NetworkLab', 'Skeleton', 'NOT_IMPLEMENTED',
                'sh install.sh', 'netlab-c', 'netlab-s',
                'self-test')
    for phrase in required:
        check(phrase in raw, 'README missing disclosure/instruction: ' + phrase)
    if version is not None:
        check(('NetworkLab v' + version + ' Skeleton') in raw,
              'README version differs from lib/common.sh')
    check('343 43 43 4' not in raw, 'README still contains corrupted placeholder content')


def audit_source(root):
    check(root.is_dir() and not root.is_symlink(), 'source directory missing or symlinked')
    for name in REQUIRED + WORKERS:
        f = root / name
        check(f.is_file() and not f.is_symlink() and f.stat().st_size > 0,
              'missing, empty or symlinked required file: ' + name)
    ver = get_version((root / 'lib/common.sh').read_text('utf-8'))
    validate_readme((root / 'README.md').read_text('utf-8'), ver)
    for name in WORKERS:
        content = (root / name).read_bytes()[:1024]
        check((b'NETLAB_IMPLEMENTED_V1' in content) == (name in IMPLEMENTED_WORKERS),
              'Worker implementation marker differs from reviewed D01/D02 roster: ' + name)
    # Only invoke the version-only entrypoints; they never probe or mutate.
    for role in ('c', 's'):
        p = subprocess.run(['bash', str(root / ('netlab-' + role + '.sh')), '--version'],
                           cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=12, check=False)
        check(p.returncode == 0 and ('NetworkLab v' + ver).encode() in p.stdout,
              'CLI/version inconsistency for ' + role)
    return ver


def parse_sha_sidecar(path, basename):
    check(path.is_file() and not path.is_symlink() and path.stat().st_size <= 8192,
          'missing or unsafe checksum sidecar')
    try:
        line = path.read_text('ascii').strip()
    except (UnicodeError, OSError):
        raise AuditError('invalid checksum sidecar encoding')
    parts = line.split()
    check(len(parts) in (1, 2) and SHA_RE.fullmatch(parts[0]) is not None,
          'invalid SHA-256 sidecar format')
    if len(parts) == 2:
        check(parts[1].lstrip('*') == basename, 'SHA-256 filename mismatch')
    return parts[0].lower()


def inspect_zip(blob, tag):
    check(len(blob) <= MAX_ZIP_BYTES, 'Release ZIP too large')
    import io
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except (zipfile.BadZipFile, OSError) as exc:
        raise AuditError('invalid Release ZIP: ' + str(exc))
    with z:
        infos = z.infolist()
        check(infos and len(infos) <= MAX_MEMBERS, 'too many or no ZIP entries')
        check(sum(x.file_size for x in infos) <= MAX_UNPACK_BYTES,
              'uncompressed Release too large')
        files = [x.filename for x in infos if not x.is_dir()]
        check(files, 'empty Release ZIP')
        parts = [PurePosixPath(f).parts for f in files]
        wrapper = (parts[0][0] if len(parts[0]) > 1 and
                   all(len(p) > 1 and p[0] == parts[0][0] for p in parts) and
                   parts[0][0] not in ('c', 's', 'lib', 'defaults', 'docs', 'tests', 'schemas', 'scripts')
                   else None)
        names = {}
        seen = set()
        for item in infos:
            name = item.filename
            check(not ('\\' in name or '\x00' in name or ':' in name or name.startswith('/')),
                  'unsafe ZIP filename')
            raw = name.rstrip('/')
            check(not any(part in ('', '.', '..') for part in raw.split('/')),
                  'ZIP contains path traversal or invalid path component')
            p = PurePosixPath(raw)
            if wrapper:
                check(p.parts[0] == wrapper, 'inconsistent ZIP wrapper')
                p = PurePosixPath(*p.parts[1:])
                if str(p) == '.':
                    continue
            normalized = str(p)
            key = normalized.casefold()
            check(key not in seen, 'duplicate/case-colliding ZIP entry: ' + normalized)
            seen.add(key)
            ftype = stat.S_IFMT(item.external_attr >> 16)
            check(ftype in (0, stat.S_IFREG, stat.S_IFDIR),
                  'ZIP contains symlink/special file: ' + normalized)
            check(not normalized.startswith(('.git/', '.networklab/', '__pycache__/')) and
                  '/__pycache__/' not in normalized and not normalized.endswith('.pyc'),
                  'ZIP includes development/private artifacts: ' + normalized)
            if not item.is_dir():
                names[normalized] = item
        for name in REQUIRED + WORKERS:
            check(name in names, 'Release ZIP missing required file: ' + name)
        actual = get_version(z.read(names['lib/common.sh']).decode('utf-8'))
        check('v' + actual == tag, 'Release Tag differs from ZIP source NETLAB_VERSION')
        validate_readme(z.read(names['README.md']).decode('utf-8'), actual)
        for name in WORKERS:
            check((b'NETLAB_IMPLEMENTED_V1' in z.read(names[name])[:1024]) == (name in IMPLEMENTED_WORKERS),
                  'Release worker implementation marker differs from reviewed D01/D02 roster: ' + name)
    return actual


def audit_assets(archive, checksum, tag):
    check(TAG_RE.fullmatch(tag) is not None, 'expected pinned semantic version tag vX.Y.Z')
    check(archive.name == 'networklab-' + tag + '.zip', 'unexpected Release ZIP filename')
    check(checksum.name == archive.name + '.sha256', 'unexpected SHA-256 sidecar filename')
    check(archive.is_file() and not archive.is_symlink(), 'missing or unsafe Release ZIP')
    check(archive.stat().st_size <= MAX_ZIP_BYTES, 'Release ZIP too large')
    want = parse_sha_sidecar(checksum, archive.name)
    blob = archive.read_bytes()
    check(hashlib.sha256(blob).hexdigest() == want, 'Release SHA-256 mismatch')
    return inspect_zip(blob, tag)


def audit_online(source, tag, repo):
    check(TAG_RE.fullmatch(tag) is not None, 'online check requires pinned tag')
    check(repo == 'xlldll/NetworkLab', 'C07 online verification pinned to official repository')
    # Import the project's hardened GitHub URL transport rather than introducing
    # a second downloader with less strict redirect and size checks.
    spec = importlib.util.spec_from_file_location('netlab_updater', str(source / 'lib/updater.py'))
    check(spec is not None and spec.loader is not None, 'updater module unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = module.release_metadata(repo, tag)
    archive_url, sidecar_url = module.release_asset_urls(repo, metadata, tag)
    archive_name = 'networklab-' + tag + '.zip'
    wanted = module.get_expected_digest(module.url_bytes(sidecar_url, module.MAX_CHECKSUM), archive_name)
    blob = module.url_bytes(archive_url, module.MAX_ZIP)
    check(hashlib.sha256(blob).hexdigest() == wanted, 'downloaded Release ZIP SHA-256 mismatch')
    return inspect_zip(blob, tag)


def main(argv=None):
    parser = argparse.ArgumentParser(description='C07 release readiness (offline unless --online)')
    parser.add_argument('--source', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--asset', type=Path)
    parser.add_argument('--checksum', type=Path)
    parser.add_argument('--tag')
    parser.add_argument('--online', action='store_true', help='explicit GitHub Release read-only audit')
    parser.add_argument('--repo', default='xlldll/NetworkLab')
    args = parser.parse_args(argv)
    if bool(args.asset) != bool(args.checksum):
        parser.error('--asset and --checksum must be supplied together')
    if (args.asset or args.online) and not args.tag:
        parser.error('a pinned --tag is required for Release inspection')
    root = Path(args.source).resolve()
    try:
        ver = audit_source(root)
        print('[PASS] C07 source, README, CLI version and eight Skeleton workers and one D01 inventory: v' + ver, flush=True)
        if args.asset or args.online:
            check(args.tag == 'v' + ver, 'source NETLAB_VERSION differs from requested Release Tag')
        if args.asset:
            rel_ver = audit_assets(args.asset, args.checksum, args.tag)
            print('[PASS] C07 local Release asset + SHA-256: v' + rel_ver, flush=True)
        if args.online:
            rel_ver = audit_online(root, args.tag, args.repo)
            print('[PASS] C07 official GitHub Release + SHA-256: v' + rel_ver, flush=True)
        print('[C07] PASS: read-only release audit (CI code gate; field acceptance is separate)', flush=True)
        return 0
    except (AuditError, OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as exc:
        print('[C07] FAIL: ' + str(exc), file=sys.stderr, flush=True)
        return 1
    except Exception as exc:
        # Keep offline CI diagnosis useful when the remote GitHub transport fails.
        print('[C07] FAIL: ' + type(exc).__name__ + ': ' + str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
