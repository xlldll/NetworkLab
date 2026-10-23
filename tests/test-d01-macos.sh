#!/bin/sh
# D01 Stage 1: macOS contract verification. No live VPS or Linux sysfs reads.
set -eu
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Darwin ]; then
  echo '[D01 MAC] wrong host platform: expected macOS' >&2
  exit 2
fi
printf '[D01 MAC] source commit: '
git rev-parse HEAD
sh tests/test-d01-all.sh
sh tests/test-c07-all.sh
bash tests/test-b11-all.sh
sh tests/test-c04-all.sh
sh tests/test-c05-all.sh
python3 -B tests/test-c01-macos.py
printf '\n[D01 MAC] PASS (Linux S inventory skipped by design, not field verified)\n'
