#!/usr/bin/env bash
# Portable tests for NetworkLab B02. No network, no config mutation.
# Force non-interactive stdin: running this from Terminal must not change the expectations.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HARNESS="$ROOT/tests/cli-harness.sh"
pass=0
fail=0

expect_code() {
  local wanted="$1" actual
  shift
  "$HARNESS" "$@" </dev/null >/dev/null 2>/dev/null
  actual=$?
  if [ "$actual" -eq "$wanted" ]; then
    pass=$((pass+1))
  else
    fail=$((fail+1))
    printf 'FAIL expected %s got %s: ' "$wanted" "$actual" >&2
    printf '%q ' "$@" >&2
    printf '\n' >&2
  fi
}
expect_output() {
  local expected="$1" text
  shift
  text="$("$HARNESS" "$@" </dev/null 2>/dev/null)"
  if [ "$?" -eq 0 ] && [[ "$text" == *"$expected"* ]]; then
    pass=$((pass+1))
  else
    fail=$((fail+1))
    printf 'FAIL output must contain <%s>, got <%s>\n' "$expected" "$text" >&2
  fi
}

# Global flags and no-argv behavior; non-TTY must not open menu.
expect_code 0 c --help
expect_code 0 s --version
expect_code 2 c
expect_code 2 s
expect_code 2 c --not-a-flag
expect_code 2 x --help
expect_code 0 c inventory --help
expect_code 0 s toolbox --version
expect_output 'NetworkLab Client' c --help
expect_output 'CLI contract' s --version

# C route registry; never execute corresponding operations.
expect_code 0 c targets list
expect_code 0 c targets show nat-us
expect_code 0 c targets validate
expect_code 0 c config validate
expect_code 0 c results list
expect_code 0 c results show abc-run
expect_code 0 c logs list
expect_code 0 c doctor
expect_code 0 c self-test
expect_code 0 c update check
expect_code 0 c update apply --version v0.1.1
expect_code 0 c paired --target nat-us --profile standard --non-interactive
expect_code 0 c collect --target nat-us --non-interactive
expect_code 0 c standalone --profile deep --dry-run
expect_code 0 c proxy --profile quick
expect_output 'target=nat-us' c paired --profile quick --target nat-us --quiet --non-interactive
expect_output 'limit=20' c results list
expect_output 'limit=5' c results list --limit 005

# Group help is available without config; execution without a subcommand is not.
expect_code 0 c targets --help
expect_code 0 s schedule --help
expect_code 0 c config --help
expect_code 0 s results --help
expect_code 0 c update --version
expect_code 2 c targets
expect_code 2 s schedule
expect_code 2 c config
expect_code 2 s update
expect_output 'Example: netlab-c paired' c paired --help
expect_output 'release tag' s update apply --version v0.1.1 --help

# S route registry and limits.
expect_code 0 s inventory
expect_code 0 s toolbox --modules netquality,tcpquality --profile quick --non-interactive
expect_code 0 s toolbox --modules all --dry-run
expect_code 0 s service status
expect_code 0 s service start --dry-run
expect_code 0 s service stop
expect_code 0 s schedule list
expect_code 0 s schedule add --dry-run
expect_code 0 s schedule edit peak
expect_code 0 s schedule enable peak
expect_code 0 s schedule disable peak
expect_code 0 s schedule run peak --non-interactive
expect_code 0 s schedule logs
expect_code 0 s schedule logs peak
expect_code 0 s config profiles
expect_code 0 s config edit --editor vim
expect_code 0 s results show abc-run
expect_code 0 s update apply --version 0.2.0

# Strict errors: invalid routes, flags, values, duplicate flags.
expect_code 2 c spelling
expect_code 2 s targets list
expect_code 2 c schedule list
expect_code 2 s paired --target nat-us
expect_code 2 c targets remove nat-us
expect_code 2 c targets show
expect_code 2 s service reboot
expect_code 2 s schedule edit
expect_code 2 c results show
expect_code 2 c paired --target unknown --profile invalid
expect_code 2 c paired --target
expect_code 2 c paired --profile standard --profile quick
expect_code 2 c paired --target nat-us --target nat-uk
expect_code 2 s toolbox --modules foo
expect_code 2 s toolbox --modules netquality,netquality
expect_code 2 s toolbox --modules netquality,all
expect_code 2 s toolbox --modules 'netquality, tcpquality'
expect_code 2 s toolbox --modules
expect_code 2 s toolbox --unknown-flag
expect_code 2 c inventory --target nat-us
expect_code 2 c inventory --profile standard
expect_code 2 s config profiles --profile standard
expect_code 2 c results list --limit 0
expect_code 2 c results list --limit -1
expect_code 2 c results list --limit 1000000
expect_code 2 c targets edit --editor emacs
expect_code 2 c targets edit --non-interactive
expect_code 2 c config edit --non-interactive
expect_code 2 c paired --non-interactive
expect_code 2 c collect --non-interactive
expect_code 2 c targets add --non-interactive
expect_code 2 c update apply
expect_code 2 s update apply --version
expect_code 2 s update apply --version '$(curl evil)'
expect_code 2 c targets add --id BAD --non-interactive
expect_code 2 c targets add --name Test --id good --type nat --ipv4 192.0.2.1 --iperf-port 70000 --mtr-port 443 --non-interactive
expect_code 2 c targets show nat-us extra
expect_code 2 c proxy --profile standard trailing
expect_code 2 c paired --target nat-us --quiet --quiet
expect_code 2 c paired --target nat-us --help --help
expect_code 2 c paired --target nat-us --config
expect_code 2 s schedule run peak --target nat-us
expect_code 2 c targets add --name Foo --id 'too-' --type nat --ipv4 192.0.2.1 --iperf-port 5202 --mtr-port 443 --non-interactive
expect_code 0 c targets add --name 'Tokyo VPS' --id tokyo --type direct --ipv4 203.0.113.20 --ipv6 '' --iperf-port 5202 --mtr-port 443 --ssh-alias tokyo --non-interactive
expect_code 0 c targets add --name 'IPv6 Only' --id ipv6-only --type nat --ipv4 '' --ipv6 '2001:db8::1' --iperf-port 5222 --mtr-port 443 --non-interactive
expect_code 0 c targets add --name 'Test' --id ok --type nat --ipv4 192.0.2.1 --iperf-port 05202 --mtr-port 443 --non-interactive

printf 'CLI tests: %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
