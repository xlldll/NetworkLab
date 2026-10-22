#!/usr/bin/env bash
# B05 full local regression; no network measurements.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
bash tests/test-b01-b02.sh
python3 -S tests/test-b03-b04.py
python3 -S tests/test-b05.py
