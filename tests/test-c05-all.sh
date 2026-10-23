#!/bin/sh
# C05 single-purpose isolated acceptance, no sudo/network/probes or full-suite timeout.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 -B "$HERE/test-c05-recovery.py" "$@"
