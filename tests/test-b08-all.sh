#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash tests/test-b07-all.sh
python3 -S tests/test-b08.py
printf '\n[NetworkLab] B01-B08 all tests passed.\n'
