#!/bin/sh
# C07 static source / staged Release checks, no external network or user-data writes.
set -eu
cd "$(dirname "$0")/.."
python3 -B scripts/release_audit.py
python3 -B tests/test-c07-release.py
