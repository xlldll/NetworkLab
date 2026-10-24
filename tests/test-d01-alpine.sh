#!/bin/sh
# Backward-compatible Alpine entrypoint. D01 core by default; --full is optional.
set -eu
cd "$(dirname "$0")/.."
exec sh tests/test-d01.sh --expect alpine "$@"
