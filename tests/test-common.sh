#!/usr/bin/env bash
# No network. Only a temporary private directory is created.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/lib/common.sh"
pass=0
fail=0
ok() {
  if "$@"; then pass=$((pass+1)); else fail=$((fail+1)); printf 'FAIL: %s\n' "$*" >&2; fi
}
eq() { [ "$1" = "$2" ]; }
contains() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/networklab-b01-XXXXXXXX")" || exit 1
trap 'rm -rf "$test_dir"' EXIT

now="$(netlab_now_utc8)"
filename_time="$(netlab_filename_time_utc8)"
ok contains "$now" '+08:00'
ok contains "$now" 'T'
ok eq "${#now}" 25
ok eq "${#filename_time}" 19
ok eq "$(netlab_status_from_exit_code 0)" completed
ok eq "$(netlab_status_from_exit_code 6)" timeout
ok eq "$(netlab_status_from_exit_code 8)" not_implemented
ok eq "$(netlab_status_from_exit_code 130)" interrupted
ok eq "$(netlab_status_from_exit_code 1)" failed

NETLAB_HOME="$test_dir/home"
export NETLAB_HOME
ok eq "$(netlab_resolve_home)" "$test_dir/home"
ok eq "$(netlab_local_path config)" "$test_dir/home/config"
ok eq "$(netlab_local_path results)" "$test_dir/home/results"
ok netlab_mkdir_private "$test_dir/private"
ok test -d "$test_dir/private"
NETLAB_LOG_FILE="$test_dir/private/app.log"
export NETLAB_LOG_FILE
ok netlab_log INFO 'unit test safe message'
ok test -f "$NETLAB_LOG_FILE"
ok contains "$(cat "$NETLAB_LOG_FILE")" 'unit test safe message'
ok eq "$(stat -c %a "$NETLAB_LOG_FILE" 2>/dev/null || stat -f %Lp "$NETLAB_LOG_FILE")" 600

NETLAB_HOME='relative/path'
if netlab_resolve_home >/dev/null 2>&1; then fail=$((fail+1)); else pass=$((pass+1)); fi
NETLAB_LOG_FILE='relative/log'
if netlab_log WARN 'should fail' >/dev/null 2>&1; then fail=$((fail+1)); else pass=$((pass+1)); fi
printf 'Common tests: %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
