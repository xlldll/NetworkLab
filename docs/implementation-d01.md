# D01：S Inventory 唯讀本機實況採集

## 1. Scope and baseline

- Review baseline: `main` commit `b281e97e774ebbae65386a31b543411393862282` (2026-10-23 review).
- Status: Phase D development increment; **not a tagged Release**, does not alter v0.1.1 Tag.
- Implemented worker: `s/s-inventory.sh` only; eight other workers remain placeholders.
- Platforms: Linux VPS (Debian 12/Ubuntu/Alpine 3.21 and similar); Python >=3.8 and Bash.
- No active packets or remote tests. No `sudo`, `sysctl -w`, SSH, iperf3, or service changes.

## 2. Evidence produced

`netlab-s inventory --non-interactive` runs through existing CLI + Runner and B06
`validate_context()`, then reads only local system interfaces:

- `/etc/os-release`, `platform.uname`-derived kernel and architecture, logical CPU count, CPU model if readable.
- `/sys/class/net` interface name, operational status, MTU and *reported* link speed; Linux ioctl for primary IPv4;
  `/proc/net/if_inet6` IPv6 addresses.
- `/proc/sys/net/ipv4` TCP congestion control, available controls and TCP receive/send buffers;
  `/proc/sys/net/core/default_qdisc` if readable.
- `/proc/<pid>/comm` process-name visibility counts for xray, sing-box, iperf3. This is not a service availability check.
- DMI product-name **hint** only, not proof of virtualization technology.

Raw `s-static.json` and `worker-report.json` are written exclusively in the
Runner's private workspace; the existing `lib/report.py` alone publishes Manifest,
Summary, Raw and verified SHA-256. `synthetic=false` reflects actual local OS
observations; metrics are not throughput or packet-loss measurements.

Null means unreadable/unknown, not zero. A reported NIC speed is **not** observed
Internet throughput. The current first implementation reports the primary IPv4
address and observed IPv6 addresses in the raw evidence; keep results private when
collecting/sharing across machines. No credentials or hostnames are intentionally read.

## 3. Status contract

- `0`: completed, one observed `s-static` test and one private raw capture.
- `4`: Linux platform unavailable (for internal runner on non-Linux).
- `5`: failed real system read/write or bounded output protection.
- `8`: `--dry-run` still returns unavailable plan from existing Runner; no Context or report.
- `9`: worker invoked with forged/invalid Context.
- Existing CLI input validation codes remain unchanged. Subprocess timeout/interrupt
  remain the Runner's responsibility.

## 4. Regression compatibility

C07 Release Audit now checks explicit D01 implementation roster (one implementation,
eight placeholders), rather than rejecting all implementation markers. It still
rejects unreviewed workers pretending to be implemented. B06 and B09 pre-D01
placeholder expectations are run only on isolated copies, leaving the actual
S Inventory intact. B08's unrelated server preflight fixture targets the still-
placeholder `s-toolbox` rather than relying on an unimplemented S Inventory.

Debian C02 and Alpine C03 acceptance now require an actual non-synthetic inventory
manifest without network access. Native macOS runs fixture-only D01 tests and does
not assert that an S Worker is available on macOS.

## 5. Validation

```sh
sh tests/test-d01-all.sh
sh tests/test-c07-all.sh
bash tests/test-b11-all.sh
sh tests/test-c04-all.sh
sh tests/test-c05-all.sh
```

Linux field acceptance, in an isolated test HOME:

```sh
NETLAB_HOME="$(mktemp -d)/networklab" # install/configure under temporary HOME first
# Or simply run D01 integration tests against source:
sh tests/test-d01-all.sh
```

**CI is a code gate only.** Capture the Mac/Debian/Alpine real-device observations
separately. Do not publish a new Tag/Release until CI and applicable field tests pass.

## 6. Known limits and next increment

- Inventory is point-in-time; no active measurements of route/RTT/bandwidth.
- No qdisc per NIC (`tc`) observation in D01; `default_qdisc` is only the kernel default.
- Kernel information may be hidden in restricted containers; optional fields remain null.
- Process names are not authenticated service health; use `s-service` when implemented.
- D02 should implement macOS-side interface / route / hotspot / proxy environment inventory.

## 7. Staged field acceptance (Mac → Alpine → Debian)

Do not merge the feature branch before CI and all applicable field steps PASS.
The branch `phase-d/d01-s-inventory` triggers offline GitHub CI on push.
Run each platform's script from a checkout of the **same commit SHA**.

- macOS: `sh tests/test-d01-macos.sh` performs only client-side
  compatibility and synthetic contract checks. The Linux-only D01 integration
  test is expected to be SKIPPED.
- Alpine 3.21: `sh tests/test-d01-alpine.sh` verifies real Linux S inventory
  using a temporary NETLAB_HOME and Alpine/OpenRC safety constraints.
- Debian 12: `sh tests/test-d01-debian.sh` verifies the same real worker
  through Debian acceptance and report checks.

Record: Git commit SHA, OS/release, command, full exit code and full test
output. A successful GitHub CI run is not proof of field acceptance.
Do not run arbitrary iperf3, service operations, root commands, or live probes
as part of D01. Preserve the user’s existing NetworkLab data.
