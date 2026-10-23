#!/bin/sh
# NetworkLab B12: offline POSIX-sh installation bootstrap.
# No curl|sh, no sudo, no package-manager changes, no executable user configs.
set -eu

usage() {
  cat <<'EOF'
NetworkLab offline installer (version: see netlab-c/s --version)
Usage: sh install.sh [--role auto|c|s] [--bin-dir ABSOLUTE_PATH] [--dry-run] [--skip-self-test] [--help]

  --role auto         macOS -> Client, Linux -> Server (default)
  --role c|s          explicitly choose Client/Server (cross-platform test use)
  --bin-dir PATH      absolute location for netlab-c / netlab-s launchers
  --dry-run           preview actions without touching files
  --skip-self-test    do not run post-install offline self-test

Optional NETLAB_HOME is an absolute path overriding ~/.networklab.
The installer uses only this local source tree. Application upgrades belong to B13.
EOF
}

say_error() { printf '[NetworkLab] INSTALL_ERROR: %s\n' "$*" >&2; }
role=auto
bin_dir=
dry_run=0
skip_self_test=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --role)
      [ "$#" -ge 2 ] || { say_error '--role requires a value'; exit 2; }
      case "$2" in auto|c|s) role=$2 ;; *) say_error 'role must be auto|c|s'; exit 2 ;; esac
      shift 2 ;;
    --bin-dir)
      [ "$#" -ge 2 ] || { say_error '--bin-dir requires a value'; exit 2; }
      case "$2" in /*) bin_dir=$2 ;; *) say_error '--bin-dir must be absolute'; exit 2 ;; esac
      shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    --skip-self-test) skip_self_test=1; shift ;;
    *) say_error "unknown argument: $1"; exit 2 ;;
  esac
done

os=$(uname -s 2>/dev/null || printf unknown)
arch=$(uname -m 2>/dev/null || printf unknown)
case "$os" in
  Darwin) platform=macos; default_role=c ;;
  Linux)
    default_role=s
    platform=linux
    if [ -r /etc/os-release ]; then
      platform=$( ( . /etc/os-release; printf '%s' "${ID:-linux}" ) )
    fi ;;
  *) say_error "unsupported host OS: $os ($arch)"; exit 4 ;;
esac
[ "$role" != auto ] || role=$default_role

if ! command -v bash >/dev/null 2>&1; then
  say_error "Bash missing on $platform/$arch. Install it first: Alpine: apk add bash; Debian/Ubuntu: apt install bash; macOS: use system Bash."
  exit 4
fi
if ! command -v python3 >/dev/null 2>&1; then
  say_error "Python3 missing on $platform/$arch. Install it first: Alpine: apk add python3; Debian/Ubuntu: apt install python3; macOS: install Python 3.8+."
  exit 4
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
  say_error 'Python 3.8 or newer is required'
  exit 4
fi

source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || { say_error 'cannot locate source directory'; exit 5; }
[ -f "$source_dir/lib/installer.py" ] || { say_error 'missing trusted lib/installer.py'; exit 5; }

set -- --source "$source_dir" --role "$role" --platform "$platform" --arch "$arch"
[ -z "$bin_dir" ] || set -- "$@" --bin-dir "$bin_dir"
[ "$dry_run" -eq 0 ] || set -- "$@" --dry-run
[ "$skip_self_test" -eq 0 ] || set -- "$@" --skip-self-test
exec python3 -B -S "$source_dir/lib/installer.py" "$@"
