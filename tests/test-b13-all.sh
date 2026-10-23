#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash tests/test-b12-all.sh
python3 -B tests/test-b13.py
printf '\n[NetworkLab] B01-B13 offline regression tests passed.\n'
