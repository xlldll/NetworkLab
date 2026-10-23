#!/usr/bin/env python3
"""C06: verify CI layout and fail-closed safety contracts; offline, stdlib first.

When PyYAML is installed, parse the actual YAML structure as well. This script
never contacts GitHub, runs Docker, mutates config, or executes network probes.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / '.github/workflows/ci.yml'
REQUIRED_PATHS = (
    'tests/test-b11-all.sh', 'tests/test-b12.py', 'tests/test-b13.py',
    'tests/test-c01-macos.py', 'tests/test-c02-all.sh',
    'tests/test-c03-all.sh', 'tests/test-c04-all.sh',
    'tests/test-c05-all.sh', 'tests/test-c06-all.sh',
    'tests/ci/Dockerfile.debian12', 'tests/ci/Dockerfile.alpine321',
    'tests/ci/run-offline.sh',
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)
    print('[PASS] ' + message, flush=True)


def workflow_is_safe(source):
    forbidden = (
        r'\bpull_request_target\b', r'\bworkflow_run\s*:',
        r'\bcontents\s*:\s*write\b', r'\bactions\s*:\s*write\b',
        r'\bpermissions\s*:\s*write-all\b', r'\bsecrets\s*\.',
        r'\bsudo\b', r'\bupdate\s+apply\b', r'\bcurl\s*\|\s*(?:ba)?sh\b',
        r'\bwget\s*\|\s*(?:ba)?sh\b',
    )
    return (all(not re.search(pattern, source, re.I) for pattern in forbidden)
            and bool(re.search(r'(?m)^permissions:\s*\n\s+contents:\s*read\s*$', source))
            and bool(re.search(r'(?m)^on:\s*$', source))
            and bool(re.search(r'--network\s+none\b', source))
            and bool(re.search(r'\breadonly\b', source))
            and 'persist-credentials: false' in source)


def main():
    require(sys.version_info >= (3, 8), 'Python >= 3.8 available')
    require(WORKFLOW.is_file() and WORKFLOW.stat().st_size > 100,
            'GitHub Actions CI workflow present')
    text = WORKFLOW.read_text(encoding='utf-8')
    require(workflow_is_safe(text), 'CI security contract: read-only and no live deployments')
    require(all((REPO / x).is_file() and (REPO / x).stat().st_size > 0
                for x in REQUIRED_PATHS), 'all referenced acceptance scripts and images exist')
    require(all(text.count('tests/' + x) > 0 for x in
                ('test-b11-all.sh', 'test-b12.py', 'test-b13.py',
                 'test-c01-macos.py', 'test-c02-all.sh',
                 'test-c04-all.sh', 'test-c05-all.sh', 'test-c06-all.sh')),
            'native CI runs core regression and C01/C02/C04/C05')
    require('bash tests/test-c02-all.sh' in text,
            'C02 Bash-only entrypoint is invoked with bash, not sh')
    require(all(x in text for x in ('debian12', 'alpine321', 'run-offline.sh')),
            'separate Debian and Alpine container jobs configured')
    require('macos-15' in text and 'ubuntu-24.04' in text,
            'native GitHub runner matrix includes macOS and Ubuntu')
    require('push:' in text and 'pull_request:' in text and 'workflow_dispatch:' in text,
            'push, PR and manual triggers are enabled')
    require('timeout-minutes:' in text and 'cancel-in-progress: true' in text,
            'time limits and duplicate-run cancellation enabled')
    require('actions/checkout@v4' in text and 'actions/setup-python@v5' in text,
            'first-party checkout and Python setup used')
    require('jsonschema>=4,<5' in text and 'PyYAML>=6,<7' in text,
            'CI enables full JSON Schema and YAML validation')
    require('docker run --rm --network none' in text and '--cap-drop ALL' in text
            and '--security-opt no-new-privileges' in text,
            'container test runtime has no network or Linux capabilities')
    require('dst=/repo,readonly' in text, 'CI source mount is explicitly read-only')
    require('debian:12-slim' in (REPO / 'tests/ci/Dockerfile.debian12').read_text()
            and 'alpine:3.21' in (REPO / 'tests/ci/Dockerfile.alpine321').read_text(),
            'distribution image families pinned to Debian 12 / Alpine 3.21')
    require(all('COPY ' not in (REPO / x).read_text() for x in
                ('tests/ci/Dockerfile.debian12', 'tests/ci/Dockerfile.alpine321')),
            'images contain dependencies only, not project user data')
    runner = (REPO / 'tests/ci/run-offline.sh').read_text()
    require(all(x in runner for x in
                ('test-c02-all.sh', 'test-c03-all.sh', 'test-c04-all.sh', 'test-c05-all.sh')),
            'container runner dispatches correct distribution and common tests')
    require('bash tests/test-c02-all.sh' in runner,
            'Debian container also invokes C02 using Bash')
    require('set -eu' in runner and 'unknown distribution fixture' in runner,
            'container runner rejects unknown distribution labels')
    # Deliberate negative fixtures guard against accidental weakening of policy.
    require(not workflow_is_safe(text.replace('  contents: read', '  contents: write')),
            'negative fixture: write permissions rejected')
    require(not workflow_is_safe(text.replace('  pull_request:', '  pull_request_target:')),
            'negative fixture: privileged PR trigger rejected')
    require(not workflow_is_safe(text.replace('--network none', '--network host')),
            'negative fixture: connected test containers rejected')
    require(not workflow_is_safe(text.replace('dst=/repo,readonly', 'dst=/repo,rw')),
            'negative fixture: writable source mount rejected')
    try:
        import yaml
    except ImportError:
        print('[C06] YAML parser unavailable; structural regex checks passed; install PyYAML for full parse.')
    else:
        data = yaml.load(text, Loader=yaml.BaseLoader)
        require(isinstance(data, dict) and isinstance(data.get('jobs'), dict),
                'workflow parses as structured YAML with jobs')
        events = data['on']
        require(isinstance(events, dict) and set(events) ==
                {'push', 'pull_request', 'workflow_dispatch'},
                'YAML trigger structure allows only push, PR, manual')
        jobs = data['jobs']
        require(set(jobs) == {'native', 'distributions'},
                'YAML defines exactly two test-only job families')
        require(data.get('permissions') == {'contents': 'read'},
                'YAML grants read-only token permissions')
        require(set(jobs['distributions']['strategy']['matrix']['distro']) ==
                {'debian12', 'alpine321'},
                'YAML validates distribution job matrix')
        require(set(jobs['native']['strategy']['matrix']['os']) ==
                {'ubuntu-24.04', 'macos-15'},
                'YAML validates native macOS and Ubuntu matrix')
    print('\n[C06] STATIC PASS: CI configuration, referenced files and offline security contracts.')
    print('[C06] NOTE: actual GitHub Actions hosted runs and container builds must still be verified.')


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, OSError, ValueError) as exc:
        print('[C06] FAIL: %s' % exc, file=sys.stderr)
        sys.exit(1)
