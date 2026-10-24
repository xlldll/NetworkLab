#!/bin/sh
# NetworkLab D01: one real-host entrypoint; concise by default, optional full regression.
# No network probes, system settings changes, service operations or privilege escalation.
set -eu

usage() {
  echo 'Usage: sh tests/test-d01.sh [--full] [--expect macos|alpine|debian]' >&2
  exit 2
}

mode=core
expect=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --full) mode=full ;;
    --expect)
      [ "$#" -ge 2 ] || usage
      expect=$2
      case "$expect" in macos|alpine|debian) ;; *) usage ;; esac
      shift ;;
    *) usage ;;
  esac
  shift
done

cd "$(dirname "$0")/.."

case "$(uname -s)" in
  Darwin)
    platform=macos
    release=$(sw_vers -productVersion 2>/dev/null || uname -r)
    ;;
  Linux)
    [ -f /etc/os-release ] || { echo '[D01] FAIL: /etc/os-release missing' >&2; exit 2; }
    # /etc/os-release is trusted platform metadata provided by the local OS.
    . /etc/os-release
    release=${VERSION_ID:-unknown}
    case "${ID:-}" in
      alpine) platform=alpine ;;
      debian) platform=debian ;;
      *) echo "[D01] FAIL: unsupported Linux distribution ID=${ID:-unknown}; use D01 core directly for exploratory tests" >&2; exit 2 ;;
    esac
    ;;
  *) echo '[D01] FAIL: supported hosts are macOS, Alpine and Debian' >&2; exit 2 ;;
esac

if [ -n "$expect" ] && [ "$expect" != "$platform" ]; then
  echo "[D01] FAIL: expected $expect but detected $platform ($release)" >&2
  exit 2
fi

case "$platform:$release" in
  alpine:3.21|alpine:3.21.*|debian:12|debian:12.*|macos:*) ;;
  *) echo "[D01] NOTE: release $release is outside the D01 reference platform versions; reporting host-specific results only" ;;
esac

commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)
log_root=${TMPDIR:-/tmp}
log_root=${log_root%/}
[ -n "$log_root" ] || log_root=/tmp
umask 077
log=$(mktemp "$log_root/networklab-d01-${platform}-XXXXXXXX") || {
  echo "[D01] FAIL: cannot create private log in $log_root" >&2
  exit 5
}

printf '[D01] platform=%s release=%s commit=%s mode=%s\n' "$platform" "$release" "$commit" "$mode"

run_stage() {
  stage=$1
  shift
  printf '\n=== %s ===\n' "$stage" >> "$log"
  if "$@" >> "$log" 2>&1; then
    printf '[D01] %-18s PASS\n' "$stage"
  else
    code=$?
    printf '[D01] %-18s FAIL (exit=%s)\n' "$stage" "$code" >&2
    printf '[D01] Full log: %s\n' "$log" >&2
    tail -n 35 "$log" >&2
    exit "$code"
  fi
}

run_stage core sh tests/test-d01-all.sh
core_count=$(grep -E '^Ran [0-9]+ tests?' "$log" | tail -n 1 || true)
[ -z "$core_count" ] || printf '[D01] %s\n' "$core_count"
if [ "$platform" = macos ]; then
  printf '[D01] Linux-only integration: SKIPPED on macOS by design\n'
fi

if [ "$mode" = full ]; then
  # Historic regression is voluntary; retain independent coverage for framework changes.
  case "$platform" in
    macos)
      run_stage c07 sh tests/test-c07-all.sh
      run_stage b11 bash tests/test-b11-all.sh
      run_stage c04 sh tests/test-c04-all.sh
      run_stage c05 sh tests/test-c05-all.sh
      run_stage c01 python3 -B tests/test-c01-macos.py
      ;;
    alpine)
      run_stage c03 sh tests/test-c03-all.sh
      run_stage c07 sh tests/test-c07-all.sh
      run_stage b11 bash tests/test-b11-all.sh
      run_stage c04 sh tests/test-c04-all.sh
      run_stage c05 sh tests/test-c05-all.sh
      ;;
    debian)
      run_stage c02 bash tests/test-c02-all.sh
      run_stage c07 sh tests/test-c07-all.sh
      run_stage b11 bash tests/test-b11-all.sh
      run_stage c04 sh tests/test-c04-all.sh
      run_stage c05 sh tests/test-c05-all.sh
      ;;
  esac
fi

printf '[D01] PASS platform=%s release=%s mode=%s\n' "$platform" "$release" "$mode"
printf '[D01] Full log: %s\n' "$log"
