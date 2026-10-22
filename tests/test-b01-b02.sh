#!/usr/bin/env bash
# Aggregate local unit tests, no external dependencies or network.
set -eu
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for script in "$ROOT/lib/common.sh" "$ROOT/lib/cli.sh" "$ROOT/tests/cli-harness.sh" "$ROOT/tests/test-cli.sh" "$ROOT/tests/test-common.sh"; do
  bash -n "$script"
done
bash "$ROOT/tests/test-common.sh"
bash "$ROOT/tests/test-cli.sh"
printf 'B01/B02: all local tests passed (no network executed).\n'
