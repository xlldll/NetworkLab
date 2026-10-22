#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash tests/test-b08-all.sh
python3 -B tests/test-b09.py
printf '\n[NetworkLab] B01-B09 all local tests passed.\n'
