#!/usr/bin/env bash
# NETLAB_PLACEHOLDER_V1. B06 validated entry; no real measurements or changes.
# Public direct use is routed to the exact same CLI and Runner as the menu.
NETLAB_MODULE_ID='c-paired'
NETLAB_MODULE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 5
if [ "${NETLAB_INTERNAL_WORKER:-}" = '1' ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    printf '[NetworkLab] %s: DEPENDENCY_MISSING (4): python3\n' "$NETLAB_MODULE_ID" >&2
    exit 4
  fi
  exec python3 -S "$NETLAB_MODULE_ROOT/lib/module_entry.py" --module-id "$NETLAB_MODULE_ID"
fi
exec bash "$NETLAB_MODULE_ROOT/netlab-c.sh" paired "$@"
