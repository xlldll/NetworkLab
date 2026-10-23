#!/bin/sh
# NetworkLab C03: offline Alpine/BusyBox/OpenRC acceptance.
# This wrapper works with BusyBox ash. No live network testing or sudo.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 -B "$HERE/test-c03-alpine.py" "$@"
