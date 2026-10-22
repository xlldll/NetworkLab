#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash tests/test-b10-all.sh
python3 -B tests/test-b11.py
printf '\n[NetworkLab] B01-B11 offline regression tests passed.\n'
