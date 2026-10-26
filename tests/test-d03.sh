#!/bin/sh
# D03 manual Mac acceptance: fixtures and one real loopback TCP session.
set -eu
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Darwin ]; then
  echo '[D03] FAIL: macOS required for real-host acceptance' >&2
  exit 2
fi
umask 077
log=$(mktemp "${TMPDIR:-/tmp}/networklab-d03-macos-XXXXXXXX") || exit 5
sha=$(git rev-parse HEAD 2>/dev/null || echo unknown)
printf '[D03] platform=macos commit=%s\n' "$sha"
if python3 -B tests/test-d03.py > "$log" 2>&1; then
  count=$(grep '^Ran [0-9]* tests' "$log" | tail -n 1 || true)
  printf '[D03] core PASS; %s\n' "$count"
  printf '[D03] live loopback TCP verified; no public test endpoint contacted\n'
  printf '[D03] full log: %s\n' "$log"
else
  code=$?
  printf '[D03] FAIL (exit=%s); log=%s\n' "$code" "$log" >&2
  tail -n 35 "$log" >&2
  exit "$code"
fi
