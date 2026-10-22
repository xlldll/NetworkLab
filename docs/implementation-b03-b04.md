# NetworkLab B03／B04：C／S 互動入口實作

- Target: NetworkLab v0.1.0 Skeleton
- Status: B03／B04 entry and menu layer implemented; B05 Runner and B07／B08 configuration management **not implemented**
- Compatible design: Bash 3.2 syntax (macOS default), Python 3 stdlib (for read-only menu configuration view)
- Inputs: A03 `commands.md`, A04 `menus.md`, A05 `configuration.md`, A06 `modules.md` and B01／B02 `common.sh` + `cli.sh`

## Files

```text
netlab-c.sh                 # C CLI + interactive entry
netlab-s.sh                 # S CLI + interactive entry
lib/common.sh               # B01 unchanged, included to test integration
lib/cli.sh                  # B02 unchanged, included to test integration
lib/menu.sh                 # new C/S common terminal menus
lib/menu_data.py            # new read-only profile + targets menu view
tests/                      # B01/B02 regressions and B03/B04 interactive tests
```

Included tests: original B01/B02 regression tests, `tests/test-b03-b04.py` (PTY interaction), and `tests/test-b03-b04.sh` (combined validation).

## Installation into an existing repository

Merge these files at the matching relative paths **after comparing** any custom changes already made in your repository. Do not replace your entire repository. No private config, user results, tokens, or external tools are bundled. Do not run an unreviewed ZIP as an installation script.

```bash
# From your local NetworkLab repository after merging:
bash tests/test-b03-b04.sh
bash netlab-c.sh --help
bash netlab-s.sh --version
bash netlab-c.sh
# On a Linux VPS:
bash netlab-s.sh
```

B03/B04 do **not** install symlinks or the `netlab-c` / `netlab-s` shell aliases. The future installer is responsible for that.

## Implemented now

- Both entry scripts: source the same shared CLI parser; `--help`, `--version` work without configurations.
- No args + TTY: main menu; no args + non-TTY: usage error (2), never blocks.
- C main menu 8 options; S main menu 7 options. Navigation back with `0`; empty Enter at main menu is a no-op.
- C targets selection reads local `targets.conf` in file order; shows valid dynamic entries; default is first existing entry only inside selector; malformed entries rejected before display.
- C profile selector reads `general.default_profile` from local `c.conf`; S profile selector reads it from local `s.conf`; missing configuration defaults to standard; invalid profile fails safely.
- S Toolbox: `1,3,5`, `2-6`, `all`, empty default; maps menu indexes into stable tool IDs; rejects malformed input and deduplicates; does not run any third-party tool.
- Confirmations default NO for release upgrades and service activation; shows risk notes where relevant.
- Calls from interactive menus pass through the SAME `netlab_entry_dispatch` and B02 `netlab_cli_parse` as direct CLI calls.
- CLI preview masks nothing because the current menu only generates fixed commands and validated non-secret IDs; future secret arguments must never be printed.
- Read-only preview for `menu_data.py`; no `source`/`eval` for user configs; no network access or formal reports.
- All non-help/version commands currently return NOT_IMPLEMENTED (8), including config, targets add/edit, results, logs, doctor, self-test and update. That is **intentional at B03/B04**, not the final v0.1.0 behavior.

## Deferred deliberately

- B05: Runner, internal module invocation, validated execution Context and lifecycle.
- B06: nine standalone placeholder module entrypoints.
- B07/B08: authoritative config parser, atomic editing, full validation, management commands (`targets list`, `config validate`, etc.).
- B09/B10/B11/B12/B13: Report Writer, history/log commands, self-test, install/update.
- All actual network tests, services, schedule tasks, SSH downloads, and external tool integrations.
- Real macOS Bash 3.2, Debian/Ubuntu and Alpine target-platform acceptance tests (Phase C).

The Python helper `menu_data.py` currently provides only the read-only fields needed by interactive menus. B07/B08 should replace its parsing path with the shared authoritative config implementation instead of maintaining two separate definitions. B03/B04 do not validate settings end-to-end for actual execution.

## Exit codes

- 0: help/version/menu successfully exited.
- 2: invalid CLI invocation, or empty command with non-TTY input.
- 3: menu preview detects invalid/missing VPS configuration.
- 4: Python3 missing when a menu needs config preview.
- 8: registered but not yet implemented action.
- 130: interactive menu interrupted with Ctrl+C.

Menu invocations report child action status then return to menu, rather than exiting the program. EOF exits without spinning.

## Tests

```bash
bash tests/test-b03-b04.sh
```

Expect 123 B01/B02 regression tests plus 34 B03/B04 tests to pass in the current development environment. PTY tests use Python 3 standard library and do not connect to any network endpoint. They use a private `NETLAB_HOME` test fixture, without modifying an existing user's configuration or report files.

## Important contract note

At the end of B03/B04, the interactive shell is operational, but the feature actions are **still placeholders**. It is not correct to call NetworkLab v0.1.0 complete until B05–B13 and the target-platform acceptance criteria pass.
