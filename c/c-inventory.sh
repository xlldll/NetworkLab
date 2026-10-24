#!/usr/bin/env bash
# NETLAB_IMPLEMENTED_V1. D02 read-only macOS Client inventory.
NETLAB_MODULE_ID='c-inventory'
NETLAB_MODULE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 5
if [ "${NETLAB_INTERNAL_WORKER:-}" = '1' ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    printf '[NetworkLab] %s: DEPENDENCY_MISSING (4): python3\n' "$NETLAB_MODULE_ID" >&2
    exit 4
  fi
  exec python3 -S "$NETLAB_MODULE_ROOT/lib/c_inventory.py"
fi
exec bash "$NETLAB_MODULE_ROOT/netlab-c.sh" inventory "$@"
