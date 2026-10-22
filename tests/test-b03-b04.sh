#!/usr/bin/env bash
# B01/B02 regression + B03/B04 interactive PTY tests. No internet and no report writing.
set -eu
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for script in "$ROOT/netlab-c.sh" "$ROOT/netlab-s.sh" "$ROOT/lib/common.sh" "$ROOT/lib/cli.sh" "$ROOT/lib/menu.sh"; do
  bash -n "$script"
done
python3 -m py_compile "$ROOT/lib/menu_data.py"
bash "$ROOT/tests/test-b01-b02.sh"
python3 "$ROOT/tests/test-b03-b04.py"
printf 'All B01/B02/B03/B04 local tests passed.\n'
