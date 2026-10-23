#!/bin/sh
# D01: no external network probes, services, or root privileges.
set -eu
cd "$(dirname "$0")/.."
python3 -B tests/test-d01.py
