# C01: macOS isolated installation acceptance

## Prerequisites

This script tests a **local B13-complete checkout**. It intentionally refuses a checkout where `install.sh`, `lib/installer.py`, or `lib/updater.py` is absent/empty. It does not download code or change `~/.networklab`, `~/.local/bin`, `.zshrc`, or the GitHub repository.

Verified repository: <https://github.com/xlldll/NetworkLab>. At the time of this C01 preparation its `main` still had an empty `install.sh`, no `lib/installer.py`, no `lib/updater.py`, and no published Releases. Merge/push B12 and B13 first. This distinction is essential: a passing local test does not certify the remote GitHub branch or a real release upgrade.

## macOS acceptance

Run from the root of the updated NetworkLab checkout:

```sh
python3 -B tests/test-c01-macos.py
```

This creates an isolated temporary `HOME` and `NETLAB_HOME`, and verifies dry-run, actual C install, command launcher, all config commands, Self-test, `/bin/bash` compatibility, invalid CLI exits, repeat install data retention, official updater source configuration, and the offline pinned-update dry run. No VPS traffic or remote downloads occur. Default cleanup removes the isolated home.

To inspect a failed test's temporary home manually, rerun with `--keep` (the code is intentionally conservative about not preserving the temporary home by default).

For development on Linux only, use `--simulate`; **do not** report a Linux simulation as macOS acceptance.

## Real installed environment / release checks

After the isolated test passes, the actual user's local installation can be inspected using:

```sh
~/.local/bin/netlab-c --version
~/.local/bin/netlab-c config validate
~/.local/bin/netlab-c self-test
```

Never use the automated acceptance test on the real user's HOME. The actual GitHub Release test is still blocked until a Release exists with `networklab-vVERSION.zip` and `networklab-vVERSION.zip.sha256`; B13 GitHub Release metadata, downloaded file integrity, and rollback on macOS require an additional real-network acceptance phase.

## Acceptance report

Record OS version (`sw_vers`), CPU architecture (`uname -m`), system Bash version (`/bin/bash --version`), Python version, exact Git commit (`git rev-parse HEAD`), and complete `test-c01-macos.py` output. Personal `c.conf`, VPS IPs and credentials should not be included in a public issue or PR.
