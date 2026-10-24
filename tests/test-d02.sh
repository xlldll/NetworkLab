#!/bin/sh
# D02 one-entrypoint Mac manual acceptance. 0 = core PASS.
set -eu
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Darwin ]; then
  echo '[D02] FAIL: test-d02.sh must run on macOS' >&2
  exit 2
fi
log_root=${TMPDIR:-/tmp}
umask 077
log=$(mktemp "${log_root%/}/networklab-d02-macos-XXXXXXXX") || exit 5
sha=$(git rev-parse HEAD 2>/dev/null || echo unknown)
printf '[D02] platform=macos commit=%s\n' "$sha"
if python3 -B tests/test-d02.py > "$log" 2>&1; then
  count=$(grep '^Ran [0-9]* tests' "$log" | tail -n 1 || true)
  printf '[D02] core PASS; %s\n' "$count"
  printf '[D02] no external network probes; verified local report\n'
  printf '[D02] full log: %s\n' "$log"
else
  code=$?
  printf '[D02] core FAIL (exit=%s); log=%s\n' "$code" "$log" >&2
  tail -n 35 "$log" >&2
  exit "$code"
fi
