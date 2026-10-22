#!/usr/bin/env bash
# B02 standalone parser test harness. NOT a NetworkLab client/server entry point.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/common.sh
. "$REPO_ROOT/lib/common.sh"
# shellcheck source=../lib/cli.sh
. "$REPO_ROOT/lib/cli.sh"
role="${1:-}"
if [ "$#" -gt 0 ]; then shift; fi
netlab_cli_parse "$role" "$@"
code=$?
if [ "$code" -ne 0 ]; then exit "$code"; fi
if [ "$NETLAB_CLI_HELP" -eq 1 ]; then
  netlab_cli_print_help "$role"
elif [ "$NETLAB_CLI_SHOW_VERSION" -eq 1 ]; then
  printf 'NetworkLab v%s (CLI contract v%s)\n' "$NETLAB_VERSION" "$NETLAB_CLI_CONTRACT_VERSION"
else
  # IMPORTANT: syntax valid does not mean a NetworkLab command has executed.
  printf 'PARSE_ONLY role=%s command=%s action=%s id=%s target=%s profile=%s modules=%s quiet=%s non_interactive=%s dry_run=%s update_version=%s limit=%s\n' \
    "$NETLAB_CLI_ROLE" "$NETLAB_CLI_COMMAND" "$NETLAB_CLI_ACTION" "$NETLAB_CLI_ID" \
    "$NETLAB_CLI_TARGET" "$NETLAB_CLI_PROFILE" "$NETLAB_CLI_MODULES" \
    "$NETLAB_CLI_QUIET" "$NETLAB_CLI_NON_INTERACTIVE" "$NETLAB_CLI_DRY_RUN" \
    "$NETLAB_CLI_UPDATE_VERSION" "$NETLAB_CLI_LIMIT"
fi
