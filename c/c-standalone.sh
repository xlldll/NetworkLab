#!/usr/bin/env bash
# NETLAB_IMPLEMENTED_V1. D03 Mac TCP connect, no HTTP/TLS bytes.
NETLAB_MODULE_ID='c-standalone'
NETLAB_MODULE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 5
if [ "${NETLAB_INTERNAL_WORKER:-}" = '1' ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    printf '[NetworkLab] %s: DEPENDENCY_MISSING (4): python3\n' "$NETLAB_MODULE_ID" >&2
    exit 4
  fi
  exec python3 -S "$NETLAB_MODULE_ROOT/lib/c_tcp_connect.py"
fi
exec bash "$NETLAB_MODULE_ROOT/netlab-c.sh" standalone "$@"
