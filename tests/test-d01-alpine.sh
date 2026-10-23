#!/bin/sh
# D01 Stage 2: Linux / Alpine 3.21 real local S inventory; no network probes.
set -eu
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Linux ] || [ ! -f /etc/os-release ]; then
  echo '[D01 ALPINE] requires Linux with /etc/os-release' >&2
  exit 2
fi
. /etc/os-release
if [ "${ID:-}" != alpine ] || [ "${VERSION_ID:-}" != 3.21 ]; then
  echo '[D01 ALPINE] expected Alpine 3.21' >&2
  exit 2
fi
printf '[D01 ALPINE] source commit: '
git rev-parse HEAD
sh tests/test-d01-all.sh
sh tests/test-c03-all.sh
sh tests/test-c07-all.sh
bash tests/test-b11-all.sh
sh tests/test-c04-all.sh
sh tests/test-c05-all.sh
printf '\n[D01 ALPINE] PASS (local inventory + offline regression)\n'
