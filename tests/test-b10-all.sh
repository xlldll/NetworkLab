#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash tests/test-b09-all.sh
python3 -B tests/test-b10.py
printf '\n[NetworkLab] B01-B10 offline tests passed.\n'
