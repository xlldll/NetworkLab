#!/bin/sh
# Execute only isolated fixture tests. Called with --network none by CI.
set -eu
case "${1:-}" in
  debian12)
    bash tests/test-c02-all.sh
    ;;
  alpine321)
    sh tests/test-c03-all.sh
    ;;
  *)
    echo '[C06] unknown distribution fixture' >&2
    exit 2
    ;;
esac
sh tests/test-c04-all.sh
sh tests/test-c05-all.sh
sh tests/test-d01-all.sh
printf '\n[C06] distribution offline acceptance PASS: %s\n' "$1"
