#!/usr/bin/env bash
# NetworkLab B02: strict CLI syntax parser and command registry.
# Must be sourced after lib/common.sh. Bash >=3.2, no eval/associative arrays.
# Parsing never reads configuration, creates files, or invokes network tools.

netlab_cli_reset() {
  NETLAB_CLI_ROLE=''
  NETLAB_CLI_COMMAND=''
  NETLAB_CLI_ACTION=''
  NETLAB_CLI_ID=''
  NETLAB_CLI_PROFILE=''
  NETLAB_CLI_HAS_PROFILE=0
  NETLAB_CLI_CONFIG=''
  NETLAB_CLI_OUTPUT_DIR=''
  NETLAB_CLI_NON_INTERACTIVE=0
  NETLAB_CLI_QUIET=0
  NETLAB_CLI_DRY_RUN=0
  NETLAB_CLI_TARGET=''
  NETLAB_CLI_MODULES=''
  NETLAB_CLI_EDITOR=''
  NETLAB_CLI_LIMIT=''
  NETLAB_CLI_HELP=0
  NETLAB_CLI_SHOW_VERSION=0
  NETLAB_CLI_UPDATE_VERSION=''
  NETLAB_CLI_NAME=''
  NETLAB_CLI_ADD_ID=''
  NETLAB_CLI_TYPE=''
  NETLAB_CLI_IPV4=''
  NETLAB_CLI_IPV6=''
  NETLAB_CLI_IPERF_PORT=''
  NETLAB_CLI_MTR_PORT=''
  NETLAB_CLI_SSH_ALIAS=''
}

netlab_cli_valid_id() {
  local value="$1"
  [ "${#value}" -ge 1 ] && [ "${#value}" -le 63 ] && \
    [[ "$value" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]
}

netlab_cli_valid_port() {
  local value="$1"
  [[ "$value" =~ ^[0-9]+$ ]] || return 1
  # Decimal conversion explicit to avoid leading-zero octal interpretation.
  [ "${#value}" -le 5 ] || return 1
  [ "$((10#$value))" -ge 1 ] && [ "$((10#$value))" -le 65535 ]
}

netlab_cli_error() {
  netlab_error "USAGE_ERROR (2): $1"
  return "$NETLAB_EXIT_USAGE"
}

# Reject malformed route before checking configuration or dependencies.
netlab_cli_route_valid() {
  local role="$1" cmd="$2" action="$3" id="$4"
  case "$role:$cmd" in
    c:menu|s:menu) [ -z "$action" ] && [ -z "$id" ] ;;
    c:inventory|c:standalone|c:paired|c:proxy|c:collect|c:doctor|c:self-test|s:inventory|s:toolbox|s:doctor|s:self-test)
      [ -z "$action" ] && [ -z "$id" ] ;;
    c:targets)
      case "$action" in
        '') [ -z "$id" ] ;; # Parent command, only useful with --help/--version.
        list|validate|add|edit) [ -z "$id" ] ;;
        show) [ -n "$id" ] ;;
        *) return 1 ;;
      esac ;;
    c:config|s:config)
      case "$action" in
        '') [ -z "$id" ] ;;
        edit|validate) [ -z "$id" ] ;;
        profiles) [ "$role" = 's' ] && [ -z "$id" ] ;;
        *) return 1 ;;
      esac ;;
    c:results|s:results)
      case "$action" in
        '') [ -z "$id" ] ;;
        list) [ -z "$id" ] ;;
        show) [ -n "$id" ] ;;
        *) return 1 ;;
      esac ;;
    c:logs|s:logs) { [ -z "$action" ] || [ "$action" = list ]; } && [ -z "$id" ] ;;
    c:update|s:update) { [ -z "$action" ] || [ "$action" = check ] || [ "$action" = apply ]; } && [ -z "$id" ] ;;
    s:service)
      case "$action" in ''|status|start|stop) [ -z "$id" ] ;; *) return 1 ;; esac ;;
    s:schedule)
      case "$action" in
        '') [ -z "$id" ] ;;
        list|add) [ -z "$id" ] ;;
        edit|enable|disable|run) [ -n "$id" ] ;;
        logs) : ;; # Optional JOB_ID
        *) return 1 ;;
      esac ;;
    *) return 1 ;;
  esac
}

# List of allowed route-specific flags; --help and global --version handled separately.
netlab_cli_allowed_flags() {
  local role="$1" cmd="$2" action="$3"
  case "$cmd:$action" in
    inventory:) printf '%s' '--config --output-dir --non-interactive --quiet --dry-run' ;;
    standalone:|paired:|proxy:|toolbox:)
      printf '%s' '--profile --config --output-dir --non-interactive --quiet --dry-run'
      [ "$cmd" = paired ] && printf ' %s' '--target'
      [ "$cmd" = toolbox ] && printf ' %s' '--modules' ;;
    collect:) printf '%s' '--target --config --output-dir --non-interactive --quiet --dry-run' ;;
    targets:list|targets:show|targets:validate) printf '%s' '--config --quiet' ;;
    targets:add) printf '%s' '--config --non-interactive --quiet --dry-run --name --id --type --ipv4 --ipv6 --iperf-port --mtr-port --ssh-alias' ;;
    targets:edit|config:edit) printf '%s' '--editor --config --quiet --dry-run' ;;
    config:validate|config:profiles) printf '%s' '--config --quiet' ;;
    results:list) printf '%s' '--limit --output-dir --quiet' ;;
    results:show) printf '%s' '--output-dir --quiet' ;;
    logs:list) printf '%s' '--limit --quiet' ;;
    doctor:) printf '%s' '--config --quiet --non-interactive' ;;
    self-test:) printf '%s' '--quiet --non-interactive' ;;
    update:check) printf '%s' '--quiet' ;;
    update:apply) printf '%s' '--version --quiet --dry-run' ;;
    service:status) printf '%s' '--config --quiet' ;;
    service:start|service:stop) printf '%s' '--config --quiet --non-interactive --dry-run' ;;
    schedule:list|schedule:logs) printf '%s' '--config --quiet' ;;
    schedule:add|schedule:edit|schedule:enable|schedule:disable|schedule:run)
      printf '%s' '--config --non-interactive --quiet --dry-run' ;;
    menu:) printf '%s' '' ;;
    *) printf '%s' '' ;;
  esac
}

netlab_cli_set_option() {
  local key="$1" value="$2"
  case "$key" in
    --profile)
      case "$value" in quick|standard|deep) ;; *) netlab_cli_error "invalid profile: $value"; return 2 ;; esac
      NETLAB_CLI_PROFILE="$value"; NETLAB_CLI_HAS_PROFILE=1 ;;
    --config) NETLAB_CLI_CONFIG="$value" ;;
    --output-dir) NETLAB_CLI_OUTPUT_DIR="$value" ;;
    --non-interactive) NETLAB_CLI_NON_INTERACTIVE=1 ;;
    --quiet) NETLAB_CLI_QUIET=1 ;;
    --dry-run) NETLAB_CLI_DRY_RUN=1 ;;
    --target)
      if ! netlab_cli_valid_id "$value"; then netlab_cli_error "invalid target ID: $value"; return 2; fi
      NETLAB_CLI_TARGET="$value" ;;
    --modules)
      case "$value" in
        all) ;;
        *)
          if [[ ! "$value" =~ ^[a-z0-9-]+(,[a-z0-9-]+)*$ ]]; then
            netlab_cli_error 'modules must be comma-separated tool IDs or all'; return 2
          fi
          local entry oldifs
          oldifs="$IFS"; IFS=','
          # Word split only on comma, no eval and no glob expansion.
          read -r -a netlab_modules_tmp <<< "$value"
          IFS="$oldifs"
          local found='|'
          for entry in "${netlab_modules_tmp[@]}"; do
            case "$entry" in
              netquality|tcpquality|hardwarequality|ipquality|nexttrace|mtr|flent) ;;
              *) netlab_cli_error "unknown toolbox module: $entry"; return 2 ;;
            esac
            case "$found" in
              *"|$entry|"*) netlab_cli_error "duplicate toolbox module: $entry"; return 2 ;;
            esac
            found="$found$entry|"
          done ;;
      esac
      NETLAB_CLI_MODULES="$value" ;;
    --editor)
      case "$value" in nano|vim) NETLAB_CLI_EDITOR="$value" ;; *) netlab_cli_error 'editor must be nano or vim'; return 2 ;; esac ;;
    --limit)
      if [[ ! "$value" =~ ^[0-9]+$ ]] || [ "${#value}" -gt 6 ] || [ "$((10#$value))" -le 0 ]; then
        netlab_cli_error 'limit must be a positive integer <= 999999'; return 2
      fi
      NETLAB_CLI_LIMIT="$((10#$value))" ;;
    --name) NETLAB_CLI_NAME="$value" ;;
    --id)
      if ! netlab_cli_valid_id "$value"; then netlab_cli_error 'invalid --id'; return 2; fi
      NETLAB_CLI_ADD_ID="$value" ;;
    --type)
      case "$value" in nat|direct) NETLAB_CLI_TYPE="$value" ;; *) netlab_cli_error '--type must be nat or direct'; return 2 ;; esac ;;
    --ipv4) NETLAB_CLI_IPV4="$value" ;;
    --ipv6) NETLAB_CLI_IPV6="$value" ;;
    --iperf-port)
      if ! netlab_cli_valid_port "$value"; then netlab_cli_error 'invalid --iperf-port'; return 2; fi
      NETLAB_CLI_IPERF_PORT="$((10#$value))" ;;
    --mtr-port)
      if ! netlab_cli_valid_port "$value"; then netlab_cli_error 'invalid --mtr-port'; return 2; fi
      NETLAB_CLI_MTR_PORT="$((10#$value))" ;;
    --ssh-alias)
      if [ -n "$value" ] && [[ ! "$value" =~ ^[a-zA-Z0-9_.][a-zA-Z0-9_.-]*$ ]]; then
        netlab_cli_error 'invalid --ssh-alias'; return 2
      fi
      NETLAB_CLI_SSH_ALIAS="$value" ;;
    --version) NETLAB_CLI_UPDATE_VERSION="$value" ;;
    *) netlab_cli_error "unsupported flag: $key"; return 2 ;;
  esac
}

netlab_cli_parse() {
  local role="${1:-}" argc=0 command='' action='' id='' token key value
  local allowed='' seen='|' require_value=0 args_started=0
  netlab_cli_reset
  case "$role" in c|s) NETLAB_CLI_ROLE="$role" ;; *) netlab_cli_error 'role must be c or s'; return 2 ;; esac
  shift

  # First extract positional route segments while retaining only subsequent options.
  # Shell arguments stay quoted; nothing is evaluated as a command.
  local -a option_tokens=()
  while [ "$#" -gt 0 ]; do
    token="$1"
    if [ "$args_started" -eq 0 ] && [ "${token#--}" = "$token" ]; then
      case "$token" in
        -*) netlab_cli_error "unsupported short option: $token"; return 2 ;;
      esac
      if [ -z "$command" ]; then command="$token"
      elif [ -z "$action" ]; then action="$token"
      elif [ -z "$id" ]; then id="$token"
      else netlab_cli_error "unexpected argument: $token"; return 2
      fi
    else
      args_started=1
      option_tokens+=("$token")
    fi
    shift
  done

  # Global help/version only, no route. Avoid reading config or probing OS.
  if [ -z "$command" ]; then
    if [ "${#option_tokens[@]}" -eq 0 ]; then
      if [ -t 0 ]; then NETLAB_CLI_COMMAND=menu; return 0; fi
      netlab_cli_error 'no command in non-interactive stdin'; return 2
    fi
    if [ "${#option_tokens[@]}" -eq 1 ]; then
      case "${option_tokens[0]}" in
        --help) NETLAB_CLI_HELP=1; return 0 ;;
        --version) NETLAB_CLI_SHOW_VERSION=1; return 0 ;;
      esac
    fi
    netlab_cli_error 'expected a command, --help or --version'; return 2
  fi

  if ! netlab_cli_route_valid "$role" "$command" "$action" "$id"; then
    netlab_cli_error "invalid command route: $command ${action:+$action }${id}"
    return 2
  fi
  NETLAB_CLI_COMMAND="$command"
  NETLAB_CLI_ACTION="$action"
  NETLAB_CLI_ID="$id"

  allowed="$(netlab_cli_allowed_flags "$role" "$command" "$action")"
  # macOS system Bash 3.2 with nounset (set -u) may treat an empty
  # array expansion as unset. Never expand option_tokens[@] when empty.
  if [ "${#option_tokens[@]}" -eq 0 ]; then
    set --
  else
    set -- "${option_tokens[@]}"
  fi
  while [ "$#" -gt 0 ]; do
    key="$1"; shift
    case "$key" in
      --help)
        if [ "$NETLAB_CLI_HELP" -eq 1 ]; then netlab_cli_error 'duplicate --help'; return 2; fi
        NETLAB_CLI_HELP=1
        ;;
      --version)
        if [ "$command" != update ] || [ "$action" != apply ]; then
          if [ "$NETLAB_CLI_SHOW_VERSION" -eq 1 ]; then netlab_cli_error 'duplicate --version'; return 2; fi
          NETLAB_CLI_SHOW_VERSION=1
          continue
        fi
        # Within update apply, --version must be followed by the release tag.
        case " $allowed " in *' --version '*) ;; *) netlab_cli_error 'invalid --version usage'; return 2 ;; esac
        case "$seen" in *'|--version|'*) netlab_cli_error 'duplicate --version'; return 2 ;; esac
        seen="$seen--version|"
        if [ "$#" -eq 0 ]; then netlab_cli_error '--version requires a release value'; return 2; fi
        value="$1"; shift
        case "$value" in --*|'') netlab_cli_error '--version requires a release value'; return 2 ;; esac
        netlab_cli_set_option "$key" "$value" || return $?
        ;;
      --*)
        case " $allowed " in *" $key "*) ;; *) netlab_cli_error "flag not valid for $command ${action}: $key"; return 2 ;; esac
        case "$seen" in *"|$key|"*) netlab_cli_error "duplicate flag: $key"; return 2 ;; esac
        seen="$seen$key|"
        case "$key" in
          --non-interactive|--quiet|--dry-run) value=1 ;;
          *)
            if [ "$#" -eq 0 ]; then netlab_cli_error "missing value for $key"; return 2; fi
            value="$1"; shift
            case "$value" in --*|'')
              # --ipv4, --ipv6, --ssh-alias can explicitly be empty strings.
              if [ "$value" = '' ] && { [ "$key" = --ipv4 ] || [ "$key" = --ipv6 ] || [ "$key" = --ssh-alias ]; }; then :
              else netlab_cli_error "missing value for $key"; return 2
              fi ;;
            esac
            ;;
        esac
        netlab_cli_set_option "$key" "$value" || return $?
        ;;
      *) netlab_cli_error "unexpected argument after flags: $key"; return 2 ;;
    esac
  done

  # --help and global --version are intentionally independent of required config.
  if [ "$NETLAB_CLI_HELP" -eq 1 ] || [ "$NETLAB_CLI_SHOW_VERSION" -eq 1 ]; then return 0; fi

  # Groups require an action for actual execution. The groups themselves may show help.
  if [ -z "$action" ]; then
    case "$command" in
      targets|config|results|logs|update|service|schedule)
        netlab_cli_error "$command requires a subcommand"; return 2 ;;
    esac
  fi

  if [ "$command" = update ] && [ "$action" = apply ] && [ -z "$NETLAB_CLI_UPDATE_VERSION" ]; then
    netlab_cli_error 'update apply requires --version VERSION'; return 2
  fi
  if [ "$command" = update ] && [ "$action" = apply ]; then
    if [[ ! "$NETLAB_CLI_UPDATE_VERSION" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.-]+)?$ ]]; then
      netlab_cli_error 'invalid release version syntax'; return 2
    fi
  fi

  if { [ "$command" = paired ] || [ "$command" = collect ]; } && [ -z "$NETLAB_CLI_TARGET" ]; then
    if [ "$NETLAB_CLI_NON_INTERACTIVE" -eq 1 ] || [ ! -t 0 ]; then
      netlab_cli_error "$command requires --target when non-interactive"; return 2
    fi
  fi
  if [ "$command" = targets ] && [ "$action" = add ]; then
    if [ "$NETLAB_CLI_NON_INTERACTIVE" -eq 1 ] || [ ! -t 0 ]; then
      if [ -z "$NETLAB_CLI_NAME" ] || [ -z "$NETLAB_CLI_ADD_ID" ] || [ -z "$NETLAB_CLI_TYPE" ] || \
         { [ -z "$NETLAB_CLI_IPV4" ] && [ -z "$NETLAB_CLI_IPV6" ]; } || \
         [ -z "$NETLAB_CLI_IPERF_PORT" ] || [ -z "$NETLAB_CLI_MTR_PORT" ]; then
        netlab_cli_error 'targets add requires name/id/type/IP/iperf-port/mtr-port when non-interactive'; return 2
      fi
    fi
  fi
  if [ "$NETLAB_CLI_NON_INTERACTIVE" -eq 1 ] && { [ "$command" = config ] && [ "$action" = edit ] || [ "$command" = targets ] && [ "$action" = edit ]; }; then
    netlab_cli_error 'edit requires an interactive terminal'; return 2
  fi
  # Set safe defaults without reading user config: B07/B08 will replace from validated INI.
  if [ -z "$NETLAB_CLI_LIMIT" ] && { [ "$command" = results ] || [ "$command" = logs ]; } && [ "$action" = list ]; then
    NETLAB_CLI_LIMIT=20
  fi
  return 0
}

netlab_cli_print_help() {
  local role="${1:-${NETLAB_CLI_ROLE:-c}}"
  local route="${NETLAB_CLI_COMMAND:-}" action="${NETLAB_CLI_ACTION:-}"
  if [ "$role" = c ]; then
    printf 'NetworkLab Client v%s\n' "$NETLAB_VERSION"
    cat <<'USAGE'
Usage: netlab-c [command] [subcommand-or-id] [options]
Commands: inventory, standalone, paired, proxy, collect,
          targets (list|show ID|add|edit|validate),
          config (edit|validate), results (list|show RUN_ID),
          logs list, doctor, self-test, update (check|apply).
Options (where applicable): --profile quick|standard|deep,
  --config FILE, --output-dir DIR, --target ID, --non-interactive,
  --quiet, --dry-run, --help, --version.
See docs/commands.md for the full per-command option contract.
USAGE
  else
    printf 'NetworkLab Server v%s\n' "$NETLAB_VERSION"
    cat <<'USAGE'
Usage: netlab-s [command] [subcommand-or-id] [options]
Commands: inventory, toolbox, service (status|start|stop),
          schedule (list|add|edit JOB_ID|enable JOB_ID|disable JOB_ID|
                    run JOB_ID|logs [JOB_ID]),
          config (edit|validate|profiles), results (list|show RUN_ID),
          logs list, doctor, self-test, update (check|apply).
Options (where applicable): --profile quick|standard|deep,
  --config FILE, --output-dir DIR, --modules ID,ID|all,
  --non-interactive, --quiet, --dry-run, --help, --version.
See docs/commands.md for the full per-command option contract.
USAGE
  fi

  # A command-specific appendix does not require any config, tool, or network.
  case "$role:$route:$action" in
    c:paired:)
      printf '\nExample: netlab-c paired --target nat-us --profile standard --non-interactive\n' ;;
    c:collect:)
      printf '\nExample: netlab-c collect --target nat-us\n' ;;
    c:targets:|c:targets:add)
      printf '\nAdd fields: --name NAME --id ID --type nat|direct --ipv4 IP --ipv6 IP\n'
      printf '            --iperf-port PORT --mtr-port PORT [--ssh-alias ALIAS]\n'
      printf 'Example: netlab-c targets add --name Test --id test --type nat --ipv4 192.0.2.1 --iperf-port 5202 --mtr-port 443 --non-interactive\n' ;;
    s:toolbox:)
      printf '\nExample: netlab-s toolbox --modules netquality,tcpquality --profile quick --non-interactive\n' ;;
    s:schedule:)
      printf '\nExample: netlab-s schedule run peak --non-interactive\n' ;;
    c:update:apply|s:update:apply)
      printf '\nExample: netlab-%s update apply --version v0.1.1\n' "$role"
      printf 'Note: here --version requires a release tag; global netlab-%s --version displays CLI version.\n' "$role" ;;
    c:config:|s:config:)
      printf '\nExample: netlab-%s config validate\n' "$role" ;;
  esac
}
