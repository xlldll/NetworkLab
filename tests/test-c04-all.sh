#!/bin/sh
# C04 offline C/S contract acceptance. No network probes or user config writes.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 -B "$HERE/test-c04-contract.py" "$@"
