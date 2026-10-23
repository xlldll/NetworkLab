#!/usr/bin/env bash
# NetworkLab B01: shared, side-effect-free helpers unless explicitly called.
# Compatible with Bash 3.2 (macOS default) and newer Bash.
# This file contains trusted application code; NEVER source user config files.

NETLAB_VERSION='0.1.1'
NETLAB_CLI_CONTRACT_VERSION='1'
NETLAB_EXIT_SUCCESS=0
NETLAB_EXIT_USAGE=2
NETLAB_EXIT_CONFIG=3
NETLAB_EXIT_DEPENDENCY=4
NETLAB_EXIT_EXECUTION=5
NETLAB_EXIT_TIMEOUT=6
NETLAB_EXIT_PARTIAL=7
NETLAB_EXIT_NOT_IMPLEMENTED=8
NETLAB_EXIT_SAFETY=9
NETLAB_EXIT_BUSY=10
NETLAB_EXIT_INTERRUPTED=130

# Portable timezone: POSIX TZ signs are reversed, so UTC-8 = UTC+08:00.
# No clock or host timezone changes, and no tzdata dependency.
netlab_now_utc8() {
  TZ='UTC-8' date '+%Y-%m-%dT%H:%M:%S+08:00'
}

netlab_filename_time_utc8() {
  TZ='UTC-8' date '+%Y-%m-%d-%H-%M-%S'
}

netlab_error() {
  printf '[NetworkLab] ERROR: %s\n' "$*" >&2
}

netlab_warn() {
  printf '[NetworkLab] WARNING: %s\n' "$*" >&2
}

netlab_info() {
  if [ "${NETLAB_CLI_QUIET:-0}" != '1' ]; then
    printf '[NetworkLab] %s\n' "$*"
  fi
}

netlab_die() {
  local exit_code="$1"
  shift
  netlab_error "$*"
  return "$exit_code"
}

netlab_check_command() {
  command -v "$1" >/dev/null 2>&1
}

netlab_status_from_exit_code() {
  case "$1" in
    0) printf '%s\n' completed ;;
    2|3|4|5|9|10) printf '%s\n' failed ;;
    6) printf '%s\n' timeout ;;
    7) printf '%s\n' partial ;;
    8) printf '%s\n' not_implemented ;;
    130) printf '%s\n' interrupted ;;
    *) printf '%s\n' failed ;;
  esac
}

# Resolve the current user's installation directory without creating it.
# Overrides must be absolute; we do not expand user-provided shell syntax.
netlab_resolve_home() {
  if [ "${NETLAB_HOME+x}" = x ]; then
    if [ -z "$NETLAB_HOME" ]; then
      netlab_error 'NETLAB_HOME cannot be empty'
      return "$NETLAB_EXIT_CONFIG"
    fi
    case "$NETLAB_HOME" in
      /*) printf '%s\n' "$NETLAB_HOME" ;;
      *) netlab_error 'NETLAB_HOME must be an absolute path'; return "$NETLAB_EXIT_CONFIG" ;;
    esac
  else
    if [ -z "${HOME:-}" ]; then
      netlab_error 'HOME is not defined'
      return "$NETLAB_EXIT_CONFIG"
    fi
    printf '%s/.networklab\n' "${HOME%/}"
  fi
}

# Output the selected local path. Never mkdir implicitly.
netlab_local_path() {
  local base
  base="$(netlab_resolve_home)" || return $?
  case "${1:-}" in
    app|config|results|logs|tmp) printf '%s/%s\n' "$base" "$1" ;;
    '') printf '%s\n' "$base" ;;
    *) netlab_error 'Unknown local directory type'; return "$NETLAB_EXIT_USAGE" ;;
  esac
}

# Explicitly invoked private mkdir. Existing directory permissions are not silently changed.
netlab_mkdir_private() {
  local dir="$1"
  if [ -z "$dir" ]; then
    netlab_error 'Directory path is required'
    return "$NETLAB_EXIT_USAGE"
  fi
  if [ -e "$dir" ] && [ ! -d "$dir" ]; then
    netlab_error 'Path exists but is not a directory'
    return "$NETLAB_EXIT_EXECUTION"
  fi
  (umask 077; mkdir -p -- "$dir") || {
    netlab_error 'Cannot create private directory'
    return "$NETLAB_EXIT_EXECUTION"
  }
}

# B01 logger: append only application-generated text; never log secrets or full argv.
# Does nothing on disk when NETLAB_LOG_FILE is unset.
netlab_log() {
  local level="$1" message="$2" stamp
  stamp="$(netlab_now_utc8)" || return "$NETLAB_EXIT_EXECUTION"
  case "$level" in
    INFO|WARN|ERROR|DEBUG) ;;
    *) netlab_error 'Unknown log level'; return "$NETLAB_EXIT_USAGE" ;;
  esac
  if [ -n "${NETLAB_LOG_FILE:-}" ]; then
    case "$NETLAB_LOG_FILE" in
      /*) ;;
      *) netlab_error 'NETLAB_LOG_FILE must be absolute'; return "$NETLAB_EXIT_CONFIG" ;;
    esac
    # Caller creates its own trusted log directory. Do not change existing permissions.
    (umask 077; printf '%s [%s] %s\n' "$stamp" "$level" "$message" >> "$NETLAB_LOG_FILE") || {
      netlab_error 'Cannot write log file'
      return "$NETLAB_EXIT_EXECUTION"
    }
  fi
}
