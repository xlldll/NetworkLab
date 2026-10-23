#!/usr/bin/env python3
"""C04: isolated C/S CLI, configuration and non-interactive contract acceptance.

Run on macOS, Debian/Ubuntu or Alpine with Python 3.8+ and Bash.
All CLI commands use temporary HOME and NETLAB_HOME. A private source copy has
all nine measurement/service/scheduler worker scripts replaced with inert
placeholders, including when the real checkout contains implemented workers.
No external networking, service operation, sudo, git fetch or live measurement.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
REQUIRED = ('install.sh', 'netlab-c.sh', 'netlab-s.sh', 'lib/installer.py',
            'lib/runner_host.py', 'lib/config_manager.py', 'lib/server_config.py',
            'lib/cli.sh', 'lib/result_browser.py', 'lib/updater.py',
            'defaults/c.conf', 'defaults/s.conf', 'defaults/targets.conf')
PROBES = ('curl', 'wget', 'iperf3', 'mtr', 'nexttrace', 'ping', 'ssh',
          'traceroute', 'flent', 'netquality', 'tcpquality')


class Failure(Exception):
    pass


def check(condition, label, detail=''):
    if not condition:
        raise Failure('%s%s' % (label, ('\n' + detail[-3500:]) if detail else ''))
    print('[PASS] ' + label, flush=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, env, *, timeout=25, cwd=None):
    try:
        return subprocess.run([str(s) for s in args], cwd=str(cwd or REPO), env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Failure('command could not complete: %s: %s' % (args, exc))


def expect(argv, env, code, label, includes=None):
    proc = run(argv, env)
    content = proc.stdout + proc.stderr
    check(proc.returncode == code and (includes is None or includes in content),
          label, 'argv=%s; expected exit=%s, actual=%s\nstdout:\n%s\nstderr:\n%s' %
          (argv, code, proc.returncode, proc.stdout, proc.stderr))
    return proc


def stage_source(src, dest):
    """Create an independent app: never trust real workers to be offline."""
    required_dirs = ('c', 's', 'lib', 'defaults', 'schemas', 'docs', 'tests')
    for dirname in required_dirs:
        shutil.copytree(src / dirname, dest / dirname,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('install.sh', 'netlab-c.sh', 'netlab-s.sh', 'LICENSE', 'README.md'):
        if (src / name).is_file():
            shutil.copy2(src / name, dest / name)
    for role in ('c', 's'):
        modules = list((dest / role).glob('*.sh'))
        if len(modules) != (5 if role == 'c' else 4):
            raise Failure('unexpected %s module count: %s' % (role, len(modules)))
        for module in modules:
            module.write_text('#!/usr/bin/env bash\n# C04 SAFE PLACEHOLDER; NO IMPLEMENTED MARKER\nexit 8\n', encoding='utf-8')
            module.chmod(0o700)


def new_environment(root, name):
    sandbox = root / name
    user = sandbox / 'user'
    lab = user / '.networklab'
    user.mkdir(parents=True, mode=0o700)
    env = dict(os.environ, HOME=str(user), NETLAB_HOME=str(lab))
    for key in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'NETLAB_INTERNAL_WORKER',
                'NETLAB_CONTEXT_FILE', 'NETLAB_CONTEXT', 'NETLAB_WORKSPACE',
                'NETLAB_WORK_DIR', 'NETLAB_SKIP_VALIDATION', 'NETLAB_LOG_FILE'):
        env.pop(key, None)
    return lab, env


def c04(keep=False):
    check(sys.version_info >= (3, 8), 'Python >=3.8 available')
    check(shutil.which('bash') is not None and shutil.which('python3') is not None,
          'Bash and Python3 available')
    check(all((REPO / p).is_file() and (REPO / p).stat().st_size for p in REQUIRED),
          'C/S CLI, config, updater and installer source present')
    temp = Path(tempfile.mkdtemp(prefix='networklab-c04-'))
    stage = temp / 'source'
    stage.mkdir(mode=0o700)
    try:
        stage_source(REPO, stage)
        check(all(b'NETLAB_IMPLEMENTED_V1' not in p.read_bytes()[:512] for role in ('c', 's')
                  for p in (stage / role).glob('*.sh')),
              'all 9 worker paths replaced with safe no-probe placeholders')
        # Ensure anything accidentally calling common probe programs is caught:
        # candidate names are shadowed by fail-closed local stubs.
        fakebin = temp / 'probe-guard'
        fakebin.mkdir(mode=0o700)
        marker = temp / 'UNEXPECTED_NETWORK_TOOL'
        for name in PROBES:
            path = fakebin / name
            path.write_text('#!/bin/sh\nprintf "%s\\n" "$0" >> "$NETLAB_C04_PROBE_MARKER"\nprintf "UNEXPECTED_PROBE:%s\\n" "$0" >&2\nexit 98\n', encoding='ascii')
            path.chmod(0o700)
        c_lab, c_env = new_environment(temp, 'c')
        s_lab, s_env = new_environment(temp, 's')
        for env in (c_env, s_env):
            env['PATH'] = str(fakebin) + os.pathsep + env.get('PATH', '/usr/bin:/bin')
            env['NETLAB_C04_PROBE_MARKER'] = str(marker)
        guard = run([fakebin / 'curl'], c_env)
        check(guard.returncode == 98 and marker.exists() and
              'UNEXPECTED_PROBE:' in guard.stderr,
              'probe guard itself is active and fail-closed')
        marker.unlink()
        check(not (c_lab.exists() or s_lab.exists()), 'no pre-existing test application or user data')
        c_preview = expect(['sh', stage / 'install.sh', '--role', 'c', '--dry-run'],
                           c_env, 0, 'Client installer dry-run succeeds', 'DRY_RUN')
        s_preview = expect(['sh', stage / 'install.sh', '--role', 's', '--dry-run'],
                           s_env, 0, 'Server installer dry-run succeeds', 'DRY_RUN')
        check(not (c_lab.exists() or s_lab.exists()), 'both installer previews are filesystem side-effect-free')
        expect(['sh', stage / 'install.sh', '--role', 'c', '--skip-self-test'],
               c_env, 0, 'isolated Client installation', 'INSTALL PASS: C')
        expect(['sh', stage / 'install.sh', '--role', 's', '--skip-self-test'],
               s_env, 0, 'isolated Server installation', 'INSTALL PASS: S')
        c = c_lab / 'bin/netlab-c'
        s = s_lab / 'bin/netlab-s'
        c_cfg = c_lab / 'config/c.conf'
        t_cfg = c_lab / 'config/targets.conf'
        s_cfg = s_lab / 'config/s.conf'
        check(all(path.is_file() for path in (c, s, c_cfg, t_cfg, s_cfg)),
              'isolated app launchers and role-specific configs exist')
        check(all(stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
                  for path in (c_cfg, t_cfg, s_cfg)), 'all configuration files remain private (0600)')
        check(not (c_lab / 'config/s.conf').exists() and not (s_lab / 'config/c.conf').exists(),
              'Client and Server configs are role-isolated')
        c_initial = digest(c_cfg)
        s_initial = digest(s_cfg)
        t_initial = digest(t_cfg)

        # CLI syntax, contract and exit codes. DEVNULL guarantees no TTY.
        for label, tool, env in (('C', c, c_env), ('S', s, s_env)):
            expect([tool, '--help'], env, 0, label + ' global help without TTY', 'Usage:')
            expect([tool, '--version'], env, 0, label + ' version without TTY', 'NetworkLab v')
            expect([tool], env, 2, label + ' rejects implicit menu in non-TTY')
            expect([tool, 'totally-invalid'], env, 2, label + ' rejects unknown commands')
            expect([tool, 'config'], env, 2, label + ' rejects incomplete group route')
            expect([tool, 'inventory', '--nonsense'], env, 2, label + ' rejects unregistered flags')
            expect([tool, 'inventory', '--quiet', '--quiet'], env, 2, label + ' rejects repeated flags')
            expect([tool, 'inventory', '--profile', 'quick'], env, 2, label + ' rejects disallowed profile')
            expect([tool, 'inventory', '--dry-run', 'extra'], env, 2, label + ' rejects arguments after flags')
            expect([tool, 'results', 'list', '--limit', '0'], env, 2, label + ' rejects zero result limit')
            expect([tool, 'results', 'list', '--limit', '-1'], env, 2, label + ' rejects negative result limit')
            expect([tool, 'update', 'apply'], env, 2, label + ' update requires pinned version')
            expect([tool, 'update', 'apply', '--version', 'latest'], env, 2, label + ' refuses floating update version')
            expect([tool, 'config', 'edit', '--non-interactive'], env, 2,
                   label + ' refuses editor without TTY')
            expect([tool, 'config', 'edit'], env, 2, label + ' refuses implicit editor without TTY')
            expect([tool, 'results', 'list', '--limit', '3'], env, 0,
                   label + ' history listing is safe without TTY')
            expect([tool, 'logs', 'list'], env, 0, label + ' log listing is safe without TTY')
            expect([tool, 'inventory', '--non-interactive'], env, 8,
                   label + ' placeholder returns NOT_IMPLEMENTED (8)', 'NOT_IMPLEMENTED')
            expect([tool, 'inventory', '--dry-run', '--non-interactive'], env, 8,
                   label + ' dry-run placeholder returns NOT_IMPLEMENTED (8)')

        # Client config and targets manager, all inside sandbox.
        expect([c, 'config', 'validate', '--non-interactive'], c_env, 2,
               'C config validate rejects flags not in its contract')
        expect([c, 'config', 'validate'], c_env, 0, 'C config validate works', 'VALID c.conf')
        expect([c, 'targets', 'validate'], c_env, 0, 'empty targets file validates', 'VALID: 0 target(s)')
        expect([c, 'targets', 'list'], c_env, 0, 'targets list works on empty config')
        expect([c, 'targets', 'show', 'missing'], c_env, 3, 'missing target produces CONFIG_ERROR (3)')
        expect([c, 'targets', 'edit'], c_env, 2, 'C targets edit refuses missing TTY')
        expect([c, 'paired', '--non-interactive'], c_env, 2, 'C paired requires explicit target in non-TTY')
        expect([c, 'collect', '--non-interactive'], c_env, 2, 'C collect requires explicit target in non-TTY')
        expect([c, 'paired', '--target', 'Bad ID', '--non-interactive'], c_env, 2,
               'C paired rejects invalid target ID')
        expect([c, 'paired', '--target', 'missing', '--non-interactive'], c_env, 3,
               'C paired rejects unknown target without running worker')
        add = [c, 'targets', 'add', '--name', 'C04-TEST', '--id', 'c04-target', '--type', 'nat',
               '--ipv4', '192.0.2.19', '--iperf-port', '5202', '--mtr-port', '443',
               '--non-interactive']
        expect(add + ['--dry-run'], c_env, 0, 'C non-interactive add dry-run validates only', 'DRY_RUN')
        check(digest(t_cfg) == t_initial, 'targets add dry-run did not alter target config')
        expect(add, c_env, 0, 'C non-interactive targets add atomically commits', 'Added: c04-target')
        check('c04-target' in t_cfg.read_text('utf-8'), 'new Client target is present')
        inserted_digest = digest(t_cfg)
        expect([c, 'targets', 'show', 'c04-target'], c_env, 0, 'C target show reads valid record', '192.0.2.19')
        expect([c, 'targets', 'validate'], c_env, 0, 'C target file validates after add', 'VALID: 1 target(s)')
        expect(add, c_env, 3, 'C duplicate target add is rejected')
        check(digest(t_cfg) == inserted_digest, 'duplicate add does not modify target file')
        invalid = [c, 'targets', 'add', '--name', 'BAD', '--id', 'other', '--type', 'nat',
                   '--ipv4', 'not-ip', '--iperf-port', '5202', '--mtr-port', '443',
                   '--non-interactive']
        expect(invalid, c_env, 3, 'C invalid target IP is rejected')
        check(digest(t_cfg) == inserted_digest, 'invalid target does not modify existing entries')
        expect([c, 'paired', '--target', 'c04-target', '--profile', 'quick', '--non-interactive'],
               c_env, 8, 'C valid paired route reaches safe placeholder only')
        expect([c, 'collect', '--target', 'c04-target', '--non-interactive'],
               c_env, 8, 'C valid collect route reaches safe placeholder only')
        expect([c, 'standalone', '--profile', 'invalid'], c_env, 2,
               'C standalone rejects unknown profile')
        expect([c, 'standalone', '--profile', 'deep', '--non-interactive'], c_env, 8,
               'C standalone deep selection reaches placeholder')
        expect([c, 'config', 'edit', '--dry-run'], c_env, 0, 'C config editor preview is read-only', 'DRY_RUN')
        expect([c, 'targets', 'edit', '--dry-run'], c_env, 0, 'C target editor preview is read-only', 'DRY_RUN')

        # S config/profile and toolbox; schedule remains non-operational.
        expect([s, 'config', 'validate'], s_env, 0, 'S config validates', 'VALID s.conf')
        profiles = expect([s, 'config', 'profiles'], s_env, 0,
                          'S effective profiles render', '[standard]')
        check(all(p in profiles.stdout for p in ('[quick]', '[deep]', 'NOT ACTIVE')),
              'S displays three profiles and marks schedule inactive')
        expect([s, 'config', 'edit', '--dry-run'], s_env, 0, 'S editor preview is read-only', 'DRY_RUN')
        expect([s, 'toolbox', '--modules', 'not-a-tool', '--non-interactive'], s_env, 2,
               'S toolbox rejects unknown tool')
        expect([s, 'toolbox', '--modules', 'mtr,mtr', '--non-interactive'], s_env, 2,
               'S toolbox rejects duplicate modules')
        expect([s, 'toolbox', '--modules', 'mtr,nexttrace', '--profile', 'quick',
                '--non-interactive'], s_env, 8, 'S toolbox valid selection reaches placeholder')
        expect([s, 'toolbox', '--modules', 'all', '--non-interactive'], s_env, 8,
               'S toolbox all selection reaches placeholder')
        expect([s, 'service', 'status', '--non-interactive'], s_env, 2,
               'S service status rejects disallowed non-interactive flag')
        expect([s, 'service', 'status'], s_env, 8,
               'S service status is explicitly NOT_IMPLEMENTED')
        expect([s, 'schedule', 'list'], s_env, 8,
               'S scheduler is explicitly NOT_IMPLEMENTED')
        expect([s, 'schedule', 'run', 'peak', '--non-interactive'], s_env, 8,
               'S scheduler run remains a safe placeholder')

        # Verify invalid overrides fail and cannot poison actual app configs.
        bad_c = temp / 'bad-c.conf'
        bad_c.write_text(c_cfg.read_text('utf-8').replace('default_profile = standard',
                      'default_profile = invalid'), encoding='utf-8')
        expect([c, 'config', 'validate', '--config', bad_c], c_env, 3,
               'C invalid override rejected')
        bad_s = temp / 'bad-s.conf'
        bad_s.write_text(s_cfg.read_text('utf-8').replace('server_id = ', 'server_id = bad!'),
                         encoding='utf-8')
        expect([s, 'config', 'validate', '--config', bad_s], s_env, 3,
               'S invalid override rejected')
        linked = temp / 'outside-c.conf'
        linked.write_text(c_cfg.read_text('utf-8'), encoding='utf-8')
        bad_link = temp / 'linked-c.conf'
        bad_link.symlink_to(linked)
        expect([c, 'config', 'validate', '--config', bad_link], c_env, 9,
               'C configuration symlink override is blocked')
        outside_s = temp / 'outside-s.conf'
        outside_s.write_text(s_cfg.read_text('utf-8'), encoding='utf-8')
        bad_s_link = temp / 'linked-s.conf'
        bad_s_link.symlink_to(outside_s)
        expect([s, 'config', 'validate', '--config', bad_s_link], s_env, 9,
               'S configuration symlink override is blocked')
        # Deliberately hide config inside the temporary home, then restore it.
        for label, tool, env, cfg in (('C', c, c_env, c_cfg),
                                      ('S', s, s_env, s_cfg)):
            temporarily_hidden = cfg.with_name(cfg.name + '.c04-hidden')
            cfg.rename(temporarily_hidden)
            try:
                expect([tool, 'config', 'validate'], env, 3,
                       label + ' missing configuration fails closed (3)')
                # Runner intentionally treats an absent *implicit* C config as
                # optional for standalone inventory (the Client manager does not).
                expected = 8 if label == 'C' else 3
                expect([tool, 'inventory', '--non-interactive'], env, expected,
                       label + ' missing configuration follows Runner contract (%d)' % expected)
            finally:
                temporarily_hidden.rename(cfg)
        check(digest(c_cfg) == c_initial and digest(s_cfg) == s_initial,
              'all invalid overrides and editor previews preserved valid settings')
        check(digest(t_cfg) == inserted_digest, 'non-mutating CLI tests preserve target entries')
        check(not any(path for lab in (c_lab, s_lab) for path in (lab / 'results').rglob('*')),
              'no synthetic or fabricated result files were published')
        check(not any((lab / 'tmp').rglob('context.json') for lab in (c_lab, s_lab)
                      if (lab / 'tmp').exists()),
              'placeholder tests created no measurement Context')
        check(not marker.exists(), 'probe invocation marker never created')
        check(all(not p.is_symlink() for lab in (c_lab, s_lab)
                  for p in (lab / 'config').iterdir() if p.is_file()),
              'isolated configuration files remain regular files')
        print('\n[C04] PASS: CLI / configuration / non-interactive contract; '
              'offline sandbox, no probes, no user-data changes.', flush=True)
        print('[C04] Host=%s; tested C and S in separate isolated homes.' %
              sys.platform, flush=True)
    finally:
        if keep:
            print('[C04] Sandbox retained: %s' % temp, flush=True)
        else:
            shutil.rmtree(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keep', action='store_true', help='retain sandbox for inspection')
    args = parser.parse_args()
    try:
        c04(args.keep)
        return 0
    except Failure as exc:
        print('[C04] FAIL: ' + str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
