#!/usr/bin/env bash
# B05: single dispatch bridge between A03 CLI globals and the Python lifecycle host.
# Source only AFTER common.sh and cli.sh. Compatible with Bash 3.2.

netlab_runner_dispatch() {
  local role="$1" cmd="${NETLAB_CLI_COMMAND:-}" module=''
  local -a args=()
  # B07: management commands use the A03 CLI parser, but do not create a
  # measurement Run / work Context. Python treats configuration as data only.
  if [ "$role" = c ] && { [ "$cmd" = targets ] || [ "$cmd" = config ]; }; then
    if ! netlab_check_command python3; then
      netlab_error 'Python3 required for Client configuration management'
      return "$NETLAB_EXIT_DEPENDENCY"
    fi
    local home
    home="$(netlab_resolve_home)" || return $?
    args=( --home "$home" --group "$cmd" --action "${NETLAB_CLI_ACTION:-}" )
    [ -n "${NETLAB_CLI_CONFIG:-}" ] && args+=(--config "$NETLAB_CLI_CONFIG")
    [ -n "${NETLAB_CLI_ID:-}" ] && args+=(--id "$NETLAB_CLI_ID")
    [ -n "${NETLAB_CLI_EDITOR:-}" ] && args+=(--editor "$NETLAB_CLI_EDITOR")
    [ -n "${NETLAB_CLI_NAME:-}" ] && args+=(--name "$NETLAB_CLI_NAME")
    [ -n "${NETLAB_CLI_ADD_ID:-}" ] && args+=(--add-id "$NETLAB_CLI_ADD_ID")
    [ -n "${NETLAB_CLI_TYPE:-}" ] && args+=(--type "$NETLAB_CLI_TYPE")
    [ -n "${NETLAB_CLI_IPV4:-}" ] && args+=(--ipv4 "$NETLAB_CLI_IPV4")
    [ -n "${NETLAB_CLI_IPV6:-}" ] && args+=(--ipv6 "$NETLAB_CLI_IPV6")
    [ -n "${NETLAB_CLI_IPERF_PORT:-}" ] && args+=(--iperf-port "$NETLAB_CLI_IPERF_PORT")
    [ -n "${NETLAB_CLI_MTR_PORT:-}" ] && args+=(--mtr-port "$NETLAB_CLI_MTR_PORT")
    [ -n "${NETLAB_CLI_SSH_ALIAS:-}" ] && args+=(--ssh-alias "$NETLAB_CLI_SSH_ALIAS")
    [ "${NETLAB_CLI_QUIET:-0}" -eq 1 ] && args+=(--quiet)
    [ "${NETLAB_CLI_NON_INTERACTIVE:-0}" -eq 1 ] && args+=(--non-interactive)
    [ "${NETLAB_CLI_DRY_RUN:-0}" -eq 1 ] && args+=(--dry-run)
    python3 -S "$NETLAB_APP_ROOT/lib/config_manager.py" "${args[@]}"
    return $?
  fi
  # B08: Server config management uses the validated A05 INI contract.
  # It is a manager command, not a measurement Run or scheduling action.
  if [ "$role" = s ] && [ "$cmd" = config ]; then
    if ! netlab_check_command python3; then
      netlab_error 'Python3 required for Server configuration management'
      return "$NETLAB_EXIT_DEPENDENCY"
    fi
    local home
    home="$(netlab_resolve_home)" || return $?
    args=( --home "$home" --action "${NETLAB_CLI_ACTION:-}" )
    [ -n "${NETLAB_CLI_CONFIG:-}" ] && args+=(--config "$NETLAB_CLI_CONFIG")
    [ -n "${NETLAB_CLI_EDITOR:-}" ] && args+=(--editor "$NETLAB_CLI_EDITOR")
    [ "${NETLAB_CLI_QUIET:-0}" -eq 1 ] && args+=(--quiet)
    [ "${NETLAB_CLI_DRY_RUN:-0}" -eq 1 ] && args+=(--dry-run)
    python3 -S "$NETLAB_APP_ROOT/lib/server_config.py" "${args[@]}"
    return $?
  fi
  # B11: synthetic-only self-test runs in an isolated disposable app/home copy.
  # It never reads or writes live configs and never starts external probes.
  if [ "$cmd" = self-test ]; then
    if ! netlab_check_command python3; then
      netlab_error 'Python3 required for offline Self-test'
      return "$NETLAB_EXIT_DEPENDENCY"
    fi
    args=( --root "$NETLAB_APP_ROOT" --role "$role" )
    [ "${NETLAB_CLI_QUIET:-0}" -eq 1 ] && args+=(--quiet)
    [ "${NETLAB_CLI_NON_INTERACTIVE:-0}" -eq 1 ] && args+=(--non-interactive)
    python3 -B -S "$NETLAB_APP_ROOT/lib/self_test.py" "${args[@]}"
    return $?
  fi
  # B10: read-only report/log browsing, no module Run, no config dependency.
  if [ "$cmd" = results ] || [ "$cmd" = logs ]; then
    if ! netlab_check_command python3; then
      netlab_error 'Python3 required for result browsing'
      return "$NETLAB_EXIT_DEPENDENCY"
    fi
    local home
    home="$(netlab_resolve_home)" || return $?
    args=( --home "$home" --role "$role" --group "$cmd" --action "${NETLAB_CLI_ACTION:-}" )
    [ -n "${NETLAB_CLI_ID:-}" ] && args+=(--id "$NETLAB_CLI_ID")
    [ -n "${NETLAB_CLI_LIMIT:-}" ] && args+=(--limit "$NETLAB_CLI_LIMIT")
    [ -n "${NETLAB_CLI_OUTPUT_DIR:-}" ] && args+=(--output-dir "$NETLAB_CLI_OUTPUT_DIR")
    [ "${NETLAB_CLI_QUIET:-0}" -eq 1 ] && args+=(--quiet)
    python3 -S "$NETLAB_APP_ROOT/lib/result_browser.py" "${args[@]}"
    return $?
  fi
  # B13: update manager is a separate administrative action, not a test Run.
  if [ "$cmd" = update ]; then
    if ! netlab_check_command python3; then
      netlab_error 'Python3 required for pinned Release updates'
      return "$NETLAB_EXIT_DEPENDENCY"
    fi
    args=( --root "$NETLAB_APP_ROOT" --role "$role" --action "${NETLAB_CLI_ACTION:-}" )
    [ -n "${NETLAB_CLI_UPDATE_VERSION:-}" ] && args+=(--version "$NETLAB_CLI_UPDATE_VERSION")
    [ "${NETLAB_CLI_QUIET:-0}" -eq 1 ] && args+=(--quiet)
    [ "${NETLAB_CLI_DRY_RUN:-0}" -eq 1 ] && args+=(--dry-run)
    python3 -B -S "$NETLAB_APP_ROOT/lib/updater.py" "${args[@]}"
    return $?
  fi
  case "$role:$cmd" in
    c:inventory) module=c-inventory ;;
    c:standalone) module=c-standalone ;;
    c:paired) module=c-paired ;;
    c:proxy) module=c-proxy ;;
    c:collect) module=c-collect ;;
    s:inventory) module=s-inventory ;;
    s:toolbox) module=s-toolbox ;;
    s:service) module=s-service ;;
    s:schedule) module=s-scheduler ;;
    *)
      # Manager commands remain explicitly unimplemented until B07/B08 etc.
      printf '[NetworkLab] %s %s: NOT_IMPLEMENTED (8)\n' "$role" "$cmd" >&2
      return "$NETLAB_EXIT_NOT_IMPLEMENTED" ;;
  esac

  if ! netlab_check_command python3; then
    netlab_error 'Python3 required for B05 Runner'
    return "$NETLAB_EXIT_DEPENDENCY"
  fi
  args=( --root "$NETLAB_APP_ROOT" --role "$role" --command "$cmd" \
         --module "$module" --action "${NETLAB_CLI_ACTION:-}" \
         --id "${NETLAB_CLI_ID:-}" )
  [ -n "${NETLAB_CLI_CONFIG:-}" ] && args+=(--config "$NETLAB_CLI_CONFIG")
  [ -n "${NETLAB_CLI_PROFILE:-}" ] && args+=(--profile "$NETLAB_CLI_PROFILE")
  [ -n "${NETLAB_CLI_TARGET:-}" ] && args+=(--target "$NETLAB_CLI_TARGET")
  [ -n "${NETLAB_CLI_TCP_IP:-}" ] && args+=(--tcp-ip "$NETLAB_CLI_TCP_IP")
  [ -n "${NETLAB_CLI_TCP_PORT:-}" ] && args+=(--tcp-port "$NETLAB_CLI_TCP_PORT")
  [ "$role:$cmd" = c:standalone ] && args+=(--timeout-seconds 150)
  [ -n "${NETLAB_CLI_MODULES:-}" ] && args+=(--modules "$NETLAB_CLI_MODULES")
  [ -n "${NETLAB_CLI_OUTPUT_DIR:-}" ] && args+=(--output-dir "$NETLAB_CLI_OUTPUT_DIR")
  [ "${NETLAB_CLI_QUIET:-0}" -eq 1 ] && args+=(--quiet)
  [ "${NETLAB_CLI_NON_INTERACTIVE:-0}" -eq 1 ] && args+=(--non-interactive)
  [ "${NETLAB_CLI_DRY_RUN:-0}" -eq 1 ] && args+=(--dry-run)
  python3 -S "$NETLAB_APP_ROOT/lib/runner_host.py" "${args[@]}"
}
