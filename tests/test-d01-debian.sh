#!/bin/sh
# D01 Stage 3: Debian 12 real local S inventory; no network probes.
set -eu
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Linux ] || [ ! -f /etc/os-release ]; then
  echo '[D01 DEBIAN] requires Linux with /etc/os-release' >&2
  exit 2
fi
. /etc/os-release
if [ "${ID:-}" != debian ] || [ "${VERSION_ID:-}" != 12 ]; then
  echo '[D01 DEBIAN] expected Debian 12' >&2
  exit 2
fi
printf '[D01 DEBIAN] source commit: '
git rev-parse HEAD
sh tests/test-d01-all.sh
bash tests/test-c02-all.sh
sh tests/test-c07-all.sh
bash tests/test-b11-all.sh
sh tests/test-c04-all.sh
sh tests/test-c05-all.sh
printf '\n[D01 DEBIAN] PASS (local inventory + offline regression)\n'
