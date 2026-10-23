#!/usr/bin/env bash
# NETLAB_IMPLEMENTED_V1. D01 Linux VPS read-only local inventory.
# Public direct use is routed through the same CLI and Runner as menu dispatch.
NETLAB_MODULE_ID='s-inventory'
NETLAB_MODULE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 5
if [ "${NETLAB_INTERNAL_WORKER:-}" = '1' ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    printf '[NetworkLab] %s: DEPENDENCY_MISSING (4): python3\n' "$NETLAB_MODULE_ID" >&2
    exit 4
  fi
  exec python3 -S "$NETLAB_MODULE_ROOT/lib/s_inventory.py"
fi
exec bash "$NETLAB_MODULE_ROOT/netlab-s.sh" inventory "$@"
