#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash tests/test-b06-all.sh
python3 -S tests/test-b07.py
printf '\n[NetworkLab] B01-B07 all tests passed.\n'
