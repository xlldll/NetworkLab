#!/bin/sh
# C06 CI workflow offline static acceptance.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 -B "$HERE/test-c06-ci.py" "$@"
