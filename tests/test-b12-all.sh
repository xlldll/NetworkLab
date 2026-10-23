#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash tests/test-b11-all.sh
python3 -B tests/test-b12.py
printf '\n[NetworkLab] B01-B12 offline regression tests passed.\n'
