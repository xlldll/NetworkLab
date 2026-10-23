#!/usr/bin/env bash
# NetworkLab C02: run safe, isolated Debian/Ubuntu server acceptance.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -B "$HERE/test-c02-linux.py" "$@"
