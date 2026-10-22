# NetworkLab B09 hotfix + B10 Result/Log Browser

## Scope

- Fixes the macOS-sensitive B09 test `test_raw_directory_symlink_rejected`.
  The original fixture tried writing to `/etc/probe.json`, raised `PermissionError`
  before handoff, and the fake shell worker still returned 0. The new fixture
  first writes legitimate data, then replaces its `raw/` directory with a symlink
  to another **private workspace** directory. This exercises the actual B09
  report publisher's symlink rejection (expected exit 5).
- Adjusts `test_completed_report_and_schema` not to mark the whole test skipped
  when optional `jsonschema` is unavailable. All structural assertions still run;
  Draft 2020-12 validation is conditional on the optional package being installed.
- Implements read-only B10 `results list`, `results show RUN_ID`, and `logs list`
  on both C and S, without creating a test Run or loading config.

## Files to merge

```text
lib/runner.sh                  # routes results/logs to read-only browser
lib/result_browser.py         # NEW stdlib-only browser
/tests/test-b09.py            # corrected fixture and skip handling
/tests/test-b10.py            # NEW regression tests
/tests/test-b10-all.sh        # NEW aggregate test
/docs/implementation-b10.md  # this document
```

Do not replace your own `~/.networklab/config/`, `results/`, `logs/`,
`LICENSE`, or the A01/A02/A09 files. No installed test modules, proxies,
network tools, timers, or VPS services are changed.

## Public commands

```bash
bash netlab-c.sh results list
bash netlab-c.sh results list --limit 10
bash netlab-c.sh results show 2026-10-22-20-30-00-local
bash netlab-c.sh logs list
bash netlab-s.sh results list
bash netlab-s.sh logs list
```

- `results list` lists newest first but labels metadata **UNVERIFIED**; it does not
  automatically hash potentially large result files. Invalid manifest JSON is
  displayed as `INVALID` without trusting its payload.
- `results show` verifies indexed file sizes and SHA-256 values plus summary
  identity, then prints status, run UUID, tests and names/sizes of indexed files.
  It does **not** print raw file contents. SHA-256 checks integrity against the
  manifest, but do not authenticate the report's original author.
- `logs list` prints filenames only: ordinary files under `~/.networklab/logs/`,
  indexed finalized stdout/stderr files, and private worker stdout/stderr logs
  left under `~/.networklab/tmp/run-*` when a worker fails before publishing.
  It does not print potentially sensitive log contents.
- The viewer rejects a symlink result root, ignores symlink scope folders, ignores
  symlink log files, and rejects paths supplied in place of a RUN_ID.
- C and S report listings are intentionally separate. C-side imported S reports
  are not yet indexed by this version (C-Collect remains a placeholder).
- `results list`/`show` accept the existing CLI `--output-dir` override.
- Nothing in B10 deletes or modifies saved reports.

## Verification

Run from the NetworkLab repository root after merging:

```bash
bash tests/test-b10-all.sh
```

Expected: all B01–B10 offline tests pass. The B09 test no longer raises the
`PermissionError` from your macOS run.

Optional complete Draft 2020-12 Schema verification:

```bash
python3 -c 'import jsonschema; print("jsonschema available")'
```

If the optional package is missing, use a project virtual environment to install
`jsonschema`, then run `tests/test-b09.py` with that Python interpreter. The
standard test suite and the application itself do not require it.

## Boundaries

- This is file index/inspection only. It does not implement real network probes,
  missing A07 Report Writer features, SSH result downloads or log rotation.
- The B09 hotfix changes the test case, not B09's production publisher. Evidence
  from the regression test confirms the specific symlink is rejected; it is not
  a general security audit.
- The development environment tests were run on Linux. macOS Bash 3.2 and
  Alpine host-specific validation remain for C01–C03.
