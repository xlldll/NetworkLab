#!/usr/bin/env python3
"""B03/B04 read-only menu views. This is NOT the B07/B08 configuration manager.

Returns only display-safe, validated target previews and default profile.
No writes, shell evaluation, network access, or system modifications.
"""
import configparser
import ipaddress
import os
import re
import sys

ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
ALIAS_RE = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_.-]*$")
PROFILE = {"quick", "standard", "deep"}


def fail(message):
    print("[NetworkLab] CONFIG_ERROR (3): " + message, file=sys.stderr)
    return 3


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("targets", "profile") or sys.argv[2] not in ("c", "s"):
        return fail("invalid menu data call")
    action, role, root = sys.argv[1:]
    if action == "targets" and role != "c":
        return fail("targets only available on client")
    cfg = os.path.join(root, "config", "c.conf" if role == "c" else "s.conf")
    data = configparser.ConfigParser(interpolation=None, strict=True)
    if os.path.isfile(cfg):
        try:
            with open(cfg, encoding="utf-8-sig") as f:
                data.read_file(f)
        except (OSError, UnicodeError, configparser.Error) as exc:
            return fail("cannot parse configuration %s: %s" % (cfg, exc))
    if action == "profile":
        value = data.get("general", "default_profile", fallback="standard").strip()
        if value not in PROFILE:
            return fail("invalid default_profile in %s" % cfg)
        print(value)
        return 0
    target_file = data.get("paths", "targets_file", fallback="targets.conf").strip()
    if not target_file:
        return fail("paths.targets_file cannot be empty")
    target_file = os.path.join(os.path.dirname(cfg), target_file)
    if not os.path.exists(target_file):
        return fail("targets file does not exist: %s" % target_file)
    try:
        with open(target_file, encoding="utf-8-sig") as f:
            lines = f.readlines()
    except (OSError, UnicodeError) as exc:
        return fail("cannot read targets file: %s" % exc)
    targets = []
    seen = set()
    for no, line in enumerate(lines, 1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        cells = [cell.strip() for cell in raw.split("|")]
        if len(cells) != 8:
            return fail("%s:%s: target must have 8 fields" % (target_file, no))
        name, identity, kind, ipv4, ipv6, iperf, mtr, alias = cells
        if not name or len(name) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            return fail("%s:%s: invalid display name" % (target_file, no))
        if not ID_RE.fullmatch(identity) or identity in seen:
            return fail("%s:%s: invalid or duplicate target_id" % (target_file, no))
        seen.add(identity)
        if kind not in ("nat", "direct"):
            return fail("%s:%s: type must be nat or direct" % (target_file, no))
        if not ipv4 and not ipv6:
            return fail("%s:%s: IPv4 or IPv6 required" % (target_file, no))
        try:
            if ipv4:
                ipaddress.IPv4Address(ipv4)
            if ipv6:
                if "%" in ipv6 or "[" in ipv6 or "]" in ipv6:
                    raise ValueError("scoped or bracketed IPv6 not allowed")
                ipaddress.IPv6Address(ipv6)
            for port in (iperf, mtr):
                if not port.isascii() or not port.isdecimal() or not (1 <= int(port) <= 65535):
                    raise ValueError("invalid port")
        except ValueError:
            return fail("%s:%s: invalid IP address or port" % (target_file, no))
        if alias and not ALIAS_RE.fullmatch(alias):
            return fail("%s:%s: invalid SSH alias" % (target_file, no))
        family = "IPv4+IPv6" if ipv4 and ipv6 else ("IPv4" if ipv4 else "IPv6")
        # Each field is sanitized for a pipe-delimited, read-only menu view.
        print("|".join((identity, name, kind, family, ipv4, ipv6, iperf, mtr, alias)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
