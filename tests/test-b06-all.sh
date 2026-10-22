#!/usr/bin/env bash
# Full B01-B06 regression tests; never contacts public network targets.
set -e
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE"
bash tests/test-b05-all.sh
python3 -S tests/test-b06.py
printf '\n[NetworkLab] B01-B06 tests completed successfully.\n'
