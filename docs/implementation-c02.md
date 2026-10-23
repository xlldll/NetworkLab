# NetworkLab C02: Debian / Ubuntu acceptance

## Scope

C02 validates NetworkLab's already-built B12/B13 **Linux Server installation** against a real Debian or Ubuntu userspace. This does not implement network measurement modules and does not require sudo, SSH, iperf3, or network access.

The verification uses a **temporary isolated HOME and NETLAB_HOME**. It does not alter the operator's `~/.networklab`, `~/.local/bin`, shell startup configuration, live systemd services, cron jobs, or VPS network settings. The test creates only synthetic files in a private temporary directory, then removes them.

Run from a checkout that contains B12/B13:

```bash
bash tests/test-c02-all.sh
```

Or:

```bash
python3 -B tests/test-c02-linux.py
```

On failure, repeat with `--keep` to preserve a temporary test environment for investigation (it prints the path).

## Acceptance checks

- POSIX `sh` launcher and Python 3.8+ prerequisites
- OS identification (Debian/Ubuntu required; Alpine belongs to C03)
- Installer auto-detects the Server role and `--dry-run` does not touch files
- Fresh app, server configuration, command launcher, results and logs initialization
- C-only config files are not created on S installation
- Sensitive directory and file permissions exclude group/other access
- `server_id` is a valid generated `s-` identifier, not `CHANGE_ME`
- `netlab-s --help`, `--version`, `config validate`, `config profiles`, and `self-test` work
- Unknown public command returns 2; unimplemented inventory returns 8 with no fake report
- Repeat installation preserves app, s.conf, server_id, historical reports and logs
- Pinned B13 update preview remains offline and preserves files
- Symlinked configuration directory is refused without modifying outside files

## Results recorded during development

- Debian 13 (trixie), root container account: **19 checks passed**.
- Debian 13 (trixie), unprivileged `nobody` account: **19 checks passed**.
- Ubuntu 22.04 / 24.04: **not executed**; must be tested on an Ubuntu host before cross-platform sign-off.
- Live GitHub release upgrade / rollback: **not executed** here; requires two published versions or a controlled release test.
- No performance measurements were executed.

These numbers are counts of `[PASS]` checks in this test script, not a total for the entire B01–B13 regression suite.

## Deploy the new test to VPS

1. Merge the C02 incremental ZIP into the local NetworkLab repository and commit/push the new test files to `main`. This does not change the existing `v0.1.1` Release.
2. On your Debian/Ubuntu VPS, clone or pull `main`, then run:

```bash
git clone https://github.com/xlldll/NetworkLab.git
cd NetworkLab
bash tests/test-c02-all.sh
```

If the repository already exists, use `git pull --ff-only` rather than cloning again.

Do **not** assume that `v0.1.1` contains the C02 test added after release. Do not tag this test as v0.1.1 retroactively.

After isolated C02 validation, run a **separate** real-user installation acceptance on a VPS only when you want NetworkLab installed there:

```bash
sh install.sh --dry-run
sh install.sh
~/.local/bin/netlab-s config validate
~/.local/bin/netlab-s config profiles
~/.local/bin/netlab-s self-test
```

`install.sh` does not automatically upgrade an existing app. It preserves real `config/`, `results/`, `logs/`. The self-test is offline synthetic. If a VPS has less than the required Python/Bash versions, install dependencies manually, using the distro's package manager as appropriate.

## Known caveats

- On Linux, the C02 test is accepted only when `/etc/os-release` has `ID=debian` or `ID=ubuntu`.
- If C02 is run as root, it validates root's isolated environment, not non-root users. Run it as an ordinary user for that case.
- Do not run `git archive` to build a Release using unstaged/uncommitted C02 files: `git archive` uses committed tree content only.
- The `NetworkLab v0.1.0 offline installer` help text in B12 is a historical hard-coded string; verify actual installed version using `netlab-s --version`. This cosmetic mismatch should be fixed in a later patch, not by changing an already-published tag.
