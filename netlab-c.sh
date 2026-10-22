#!/usr/bin/env bash
# NetworkLab Client CLI + menu entry (B03), Bash >= 3.2.
set -u
NETLAB_APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 5
. "$NETLAB_APP_ROOT/lib/common.sh"
. "$NETLAB_APP_ROOT/lib/cli.sh"
. "$NETLAB_APP_ROOT/lib/menu.sh"
. "$NETLAB_APP_ROOT/lib/runner.sh"

netlab_entry_dispatch() {
  local role="$1" rc=0
  shift
  netlab_cli_parse "$role" "$@" || return $?
  if [ "$NETLAB_CLI_HELP" -eq 1 ]; then
    netlab_cli_print_help "$role"
    return 0
  fi
  if [ "$NETLAB_CLI_SHOW_VERSION" -eq 1 ]; then
    printf 'NetworkLab v%s (CLI contract v%s)\n' "$NETLAB_VERSION" "$NETLAB_CLI_CONTRACT_VERSION"
    return 0
  fi
  if [ "$NETLAB_CLI_COMMAND" = menu ]; then
    netlab_menu_main "$role"
    return $?
  fi
  netlab_runner_dispatch "$role"
  return $?
}

netlab_entry_dispatch c "$@"
exit $?
