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

## 7. Manual field acceptance (Mac → Alpine → Debian)

D01 core acceptance was executed on the same commit
`4ef238b9015a73f8ead38c1ef2e973b3e1b75cde`:

- macOS: contract suite PASS, one Linux-only integration SKIP as designed.
- Alpine 3.21.8: six D01 core tests PASS; previous wrapper rejected `3.21.8`
  because it compared the full version string with `3.21`.
- Debian 12: six D01 core tests PASS.

This evidence is **core acceptance**. It is not an acceptance of installed-app
service orchestration, active network tests, or the old full distro suites.

The standard field command for all three platforms is:

```sh
sh tests/test-d01.sh
```

The entrypoint auto-detects the platform, records the actual release and Git
commit, runs only D01's six tests by default, displays a concise summary and
writes a full private log to the host temporary directory. A different minor
release in the same OS family is allowed and marked as outside the reference
version rather than being incorrectly rejected; only Mac, Alpine and Debian
are D01's supported acceptance families. Prior per-platform entrypoints remain
as wrappers. Opt in to full historical regression only if needed:

```sh
sh tests/test-d01.sh --full
```

D01's tests use real read-only local Linux observations in an isolated Runner
workspace. They do not perform network probes or change services. Report
sharing can expose host IPs and should be reviewed first.

GitHub CI is **not required** for this D01 field-acceptance decision. Disable
NetworkLab CI in GitHub Actions settings if automatic runs are unwanted;
changing the local test entrypoint does not change existing workflow triggers.
The old v0.1.1 tag and the eight remaining placeholders are unchanged.
