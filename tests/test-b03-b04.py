#!/usr/bin/env python3
"""B03/B04 read-only CLI/menu integration tests using a real pseudo terminal."""
import json
import os
import pty
import re
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Version is determined from the source tree under test, not frozen to B03.
source = (ROOT / 'lib/common.sh').read_text(encoding='utf-8')
match = re.search(r"(?m)^NETLAB_VERSION='([^']+)'$", source)
if not match:
    raise SystemExit('NETLAB_VERSION missing from lib/common.sh')
EXPECTED_VERSION = match.group(1)
passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print("FAIL:", name, detail, file=sys.stderr)


def cli(role, *args, env=None):
    return subprocess.run(["bash", str(ROOT / ("netlab-" + role + ".sh")), *args],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, timeout=5)


def tty(role, commands, env, timeout=15):
    """Drive an actual TTY one prompt at a time (never pre-buffer all input).

    Sending multiple lines to a PTY before Bash starts can lose lines under
    some terminal configurations, leading to false timeouts and flaky tests.
    """
    master, slave = pty.openpty()
    proc = subprocess.Popen(["bash", str(ROOT / ("netlab-" + role + ".sh"))],
                            stdin=slave, stdout=slave, stderr=slave, env=env,
                            start_new_session=True)
    os.close(slave)
    pending = commands.splitlines(keepends=True)
    if not pending and commands:
        pending = [commands]
    buf = bytearray()
    prompt_seen_at = -1
    limit = time.monotonic() + timeout
    while time.monotonic() < limit:
        ready, _, _ = select.select([master], [], [], 0.05)
        if ready:
            try:
                data = os.read(master, 65536)
                if data:
                    buf.extend(data)
            except OSError:
                break
        if pending and len(buf) != prompt_seen_at and buf.endswith(b": "):
            cmd = pending.pop(0)
            os.write(master, cmd.encode())
            prompt_seen_at = len(buf)
        if proc.poll() is not None:
            break
    if proc.poll() is None:
        proc.kill()
    rc = proc.wait(timeout=2)
    while True:
        ready, _, _ = select.select([master], [], [], 0)
        if not ready:
            break
        try:
            block = os.read(master, 65536)
            if not block:
                break
            buf.extend(block)
        except OSError:
            break
    os.close(master)
    return rc, buf.decode(errors="replace").replace("\r", "")


with tempfile.TemporaryDirectory(prefix="netlab-b03-b04-") as temp:
    home = Path(temp) / "home"
    config = home / "config"
    config.mkdir(parents=True)
    (config / "c.conf").write_text("[general]\ndefault_profile = quick\n[paths]\ntargets_file = targets.conf\n", encoding="utf-8")
    (config / "s.conf").write_text("[general]\nconfig_version = 1\nserver_id = test-vps\ntimezone = UTC+08:00\ndefault_profile = deep\n", encoding="utf-8")
    (config / "targets.conf").write_text(
        "美西NAT|nat-us|nat|198.51.100.10||48801|443|nat-us\n"
        "東京AWS|aws-tokyo|direct|203.0.113.20|2001:db8::20|5202|443|aws-tokyo\n", encoding="utf-8")
    env = dict(os.environ, NETLAB_HOME=str(home))

    for role, expected in (("c", "Client"), ("s", "Server")):
        result = cli(role, "--help", env=env)
        check(role + " help", result.returncode == 0 and expected in result.stdout)
        result = cli(role, "--version", env=env)
        check(role + " version", result.returncode == 0 and
              ("NetworkLab v%s (CLI contract" % EXPECTED_VERSION) in result.stdout)
        result = cli(role, env=env)
        check(role + " no-TTY usage 2", result.returncode == 2)
        result = cli(role, "inventory", env=env)
        if role == "c":
            # C inventory is still an unimplemented Skeleton module.
            check("c inventory stub exit 8", result.returncode == 8 and "NOT_IMPLEMENTED" in result.stderr)
        elif sys.platform.startswith("linux"):
            # D01 S inventory performs real local OS reads without network I/O.
            check("s inventory real Linux completion", result.returncode == 0 and
                  "s-inventory: local snapshot captured" in result.stdout,
                  (result.returncode, result.stderr[-300:]))
        else:
            # macOS may run S CLI contract fixtures, not Linux-only system reads.
            check("s inventory non-Linux refuses with 4", result.returncode == 4 and
                  "Linux required" in result.stderr,
                  (result.returncode, result.stderr[-300:]))
        rc, output = tty(role, "0\n", env)
        check(role + " main 0 exit", rc == 0 and "主選單" in output, (rc, output[-400:]))
        rc, output = tty(role, "\x04", env)
        check(role + " EOF exit", rc == 0, (rc, output[-400:]))

    rc, output = tty("c", "9\n\n1\n0\n", env)
    check("C invalid/Enter remains idle/inventory dispatch", rc == 0 and "無效輸入" in output and "NOT_IMPLEMENTED" in output and "CLI: netlab-c inventory" in output)
    rc, output = tty("c", "6\n1\n0\n0\n", env)
    check("C targets submenu", rc == 0 and "CLI: netlab-c targets list" in output)
    rc, output = tty("c", "3\n2\n2\n0\n", env)
    check("C second VPS and standard profile", rc == 0 and "--target aws-tokyo" in output and "--profile standard" in output)
    rc, output = tty("c", "5\n\n0\n", env)
    check("C default first VPS", rc == 0 and "CLI: netlab-c collect --target nat-us" in output)
    rc, output = tty("c", "8\n7\nv0.1.1\n\n0\n0\n", env)
    check("C update default deny", rc == 0 and "CLI: netlab-c update apply" not in output)
    rc, output = tty("c", "8\n7\nv0.1.1\ny\n0\n0\n", env)
    check("C update explicit confirmation", rc == 0 and "CLI: netlab-c update apply --version v0.1.1" in output)
    rc, output = tty("c", "3\n6\n0\n0\n", env)
    check("C temporary target reserved", rc == 0 and "臨時 VPS: NOT_IMPLEMENTED" in output)
    rc, output = tty("c", "3\n1\n\n0\n", env)
    check("C default quick profile from config", rc == 0 and "--profile quick" in output)
    rc, output = tty("s", "2\n1,3,5\n1\ny\n0\n", env)
    check("S multi-list parsed IDs", rc == 0 and "--modules netquality\\,hardwarequality\\,nexttrace" in output and "--profile quick" in output)
    rc, output = tty("s", "2\n1,1,2\n2\ny\n0\n", env)
    check("S multi-list deduplicates", rc == 0 and "--modules netquality\\,tcpquality" in output)
    rc, output = tty("s", "2\n2-6\n\nn\n0\n", env)
    check("S ranges and Deep default, deny by n", rc == 0 and "Profile：deep" in output and "CLI: netlab-s toolbox" not in output)
    rc, output = tty("s", "2\n1,,2\n0\n0\n", env)
    check("S invalid selection refused", rc == 0 and "無效輸入" in output and "CLI: netlab-s toolbox" not in output)
    rc, output = tty("s", "3\n2\n\n0\n0\n", env)
    check("S service start confirmation default deny", rc == 0 and "CLI: netlab-s service start" not in output)
    rc, output = tty("s", "4\n4\npeak\nn\n0\n0\n", env)
    check("S scheduler enable confirmation denied", rc == 0 and "CLI: netlab-s schedule enable" not in output)
    rc, output = tty("s", "5\n1\n0\n0\n", env)
    check("S config profile handler", rc == 0 and "CLI: netlab-s config profiles" in output)

    # Targets error: invalid configuration must not silently select corrupted data.
    (config / "targets.conf").write_text("broken|id|nat|123.456.0.1||5000|443|\n", encoding="utf-8")
    rc, output = tty("c", "3\n0\n", env)
    check("C invalid targets refused", rc == 0 and "CONFIG_ERROR (3)" in output and "CLI: netlab-c paired" not in output)
    (config / "targets.conf").write_text("", encoding="utf-8")
    rc, output = tty("c", "3\n\n0\n0\n", env)
    check("C empty target no implicit default", rc == 0 and "沒有預設" in output and "CLI: netlab-c paired" not in output)
    # Dynamic list refresh and order; no hardcoded fixed VPS count.
    (config / "targets.conf").write_text(
        "One|one|nat|198.51.100.1||5202|443|one\n"
        "Two|two|direct|198.51.100.2||5202|443|two\n"
        "Three|third|direct|198.51.100.3||5202|443|third\n", encoding="utf-8")
    rc, output = tty("c", "5\n3\n0\n", env)
    check("C dynamic third VPS", rc == 0 and "--target third" in output)
    (config / "targets.conf").write_text("One|same|nat|198.51.100.1||5202|443|one\nTwo|same|direct|198.51.100.2||5202|443|two\n", encoding="utf-8")
    rc, output = tty("c", "3\n0\n", env)
    check("C duplicate IDs rejected", rc == 0 and "CONFIG_ERROR (3)" in output)
    (config / "targets.conf").write_text("One|one|nat||fe80::1%en0|5202|443|one\n", encoding="utf-8")
    rc, output = tty("c", "3\n0\n", env)
    check("C scoped IPv6 rejected", rc == 0 and "CONFIG_ERROR (3)" in output)
    (config / "s.conf").write_text("[general]\nserver_id = test-vps\ndefault_profile = supersonic\n", encoding="utf-8")
    rc, output = tty("s", "2\n1\n0\n", env)
    check("S invalid default profile blocked", rc == 0 and "CONFIG_ERROR (3)" in output and "CLI: netlab-s toolbox" not in output)
    # In Phase D, the real Linux S inventory may publish a local report.
    # All other Skeleton CLI/menu flows must remain report-free.
    if sys.platform.startswith("linux"):
        manifests = list((home / "results").rglob("*-manifest-*.json"))
        valid = len(manifests) == 1 and not (home / "results" / "c").exists()
        if valid:
            obj = json.loads(manifests[0].read_text(encoding="utf-8"))
            valid = (obj.get("module_id") == "s-inventory"
                     and obj.get("status") == "completed"
                     and obj.get("synthetic") is False
                     and obj.get("exit_code") == 0)
        check("Only non-synthetic D01 S Inventory generated a report", valid)
    else:
        check("No report from non-Linux Skeleton tests", not (home / "results").exists())

print("B03/B04 tests: %s passed, %s failed" % (passed, failed))
if failed:
    sys.exit(1)
