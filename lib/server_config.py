#!/usr/bin/env python3
"""NetworkLab B08: Server INI configuration validation and safe editing.

stdlib-only. No network access, shell interpolation, scheduler activation or tests.
Uses B07's advisory locking and file-safety primitives; writes only after full
candidate validation. The profile values are NetworkLab *abstract* modes.
"""
import argparse
import configparser
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

# Local import from the same trusted application library, not user configuration.
import config_manager as cm

EXIT_USAGE, EXIT_CONFIG, EXIT_DEP, EXIT_FAILED, EXIT_SAFETY = 2, 3, 4, 5, 9
TOOLS = ('netquality', 'tcpquality', 'hardwarequality', 'ipquality', 'nexttrace', 'mtr', 'flent')
SCHEDULE_MODULES = ('inventory',) + TOOLS
PROFILES = ('quick', 'standard', 'deep')
MODES = ('off', 'lite', 'normal', 'full')
DEFAULT_MODES = {
    'quick': ('lite', 'lite', 'off', 'lite', 'lite', 'lite', 'off'),
    'standard': ('normal', 'normal', 'lite', 'normal', 'normal', 'normal', 'off'),
    'deep': ('full', 'full', 'full', 'full', 'full', 'full', 'full'),
}
GENERAL = {'config_version', 'server_id', 'timezone', 'default_profile', 'enable_heavy_tests'}
LIMITS = {'max_metered_mb_per_run', 'max_metered_mb_per_day'}
TOOL_KEYS = {'enabled', 'profile_override'}
SCHEDULE_KEYS = {'enabled', 'time', 'days', 'profile', 'modules'}
DAYS = {'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'}
ID = cm.ID


def die(message, code=EXIT_CONFIG):
    raise cm.ConfigurationError(message, code)


def parse_bool(value, label, errors):
    text = value.strip().lower()
    if text not in ('true', 'false'):
        errors.append('%s must be true|false' % label)
        return False
    return text == 'true'


def int_nonnegative(value, label, errors):
    if not re.fullmatch(r'[0-9]{1,12}', value.strip()):
        errors.append('%s must be a non-negative integer (0..999999999999)' % label)
        return 0
    return int(value.strip())


def parse_days(raw, label, errors):
    value = raw.strip().lower()
    if value in ('daily', 'weekdays', 'weekends'):
        return value
    units = value.split(',')
    if not units or any(v not in DAYS for v in units) or len(units) != len(set(units)):
        errors.append('%s must be daily|weekdays|weekends or unique mon,tue,...,sun tokens' % label)
    return value


def parse_modules(raw, label, errors):
    values = [v.strip().lower() for v in raw.split(',')]
    if not values or any(v not in SCHEDULE_MODULES for v in values) or len(values) != len(set(values)):
        errors.append('%s must list unique supported module IDs' % label)
    return values


def validate_text(text, source='s.conf'):
    """Return normalized read-only model and human warnings, or fail code 3."""
    data = configparser.ConfigParser(interpolation=None, strict=True, inline_comment_prefixes=None)
    # Python configparser uses lowercase option keys by default.
    try:
        data.read_string(text, source=source)
    except (configparser.Error, ValueError) as exc:
        die('%s: invalid INI: %s' % (source, exc))
    errors, warnings = [], []
    if data.defaults():
        errors.append('[DEFAULT] is not supported')
    for section in data.sections():
        if section == 'general':
            allowed = GENERAL
        elif section == 'limits':
            allowed = LIMITS
        elif section.startswith('profile.') and section[8:] in PROFILES:
            allowed = set(TOOLS)
        elif section.startswith('tool.') and section[5:] in TOOLS:
            allowed = TOOL_KEYS
        elif section.startswith('schedule.') and ID.fullmatch(section[9:]):
            allowed = SCHEDULE_KEYS
        else:
            errors.append('unknown section [%s]' % section)
            continue
        for key in data.options(section):
            if key not in allowed:
                errors.append('unknown key [%s].%s' % (section, key))
    # General mandatory attributes; do not accept CHANGE_ME template verbatim.
    if not data.has_section('general'):
        errors.append('missing required [general]')
    def val(section, key, fallback=''):
        return data.get(section, key, fallback=fallback).strip()
    version = val('general', 'config_version')
    if version != '1':
        errors.append('[general].config_version must be 1')
    sid = val('general', 'server_id')
    if not ID.fullmatch(sid) or sid == 'change-me':
        errors.append('[general].server_id must be a unique lowercase device ID (CHANGE_ME is a placeholder)')
    timezone_value = val('general', 'timezone')
    if timezone_value != 'UTC+08:00':
        errors.append('[general].timezone must be UTC+08:00')
    default_profile = val('general', 'default_profile', 'standard')
    if default_profile not in PROFILES:
        errors.append('[general].default_profile must be quick|standard|deep')
    heavy = parse_bool(val('general', 'enable_heavy_tests', 'false'), '[general].enable_heavy_tests', errors)
    profiles = {}
    for profile in PROFILES:
        section = 'profile.' + profile
        profiles[profile] = {}
        for idx, tool in enumerate(TOOLS):
            mode = val(section, tool, DEFAULT_MODES[profile][idx])
            if mode not in MODES:
                errors.append('[%s].%s must be off|lite|normal|full' % (section, tool))
            profiles[profile][tool] = mode
            if not data.has_option(section, tool):
                warnings.append('[%s].%s uses built-in default %s' % (section, tool, DEFAULT_MODES[profile][idx]))
    tool_overrides = {}
    for tool in TOOLS:
        section = 'tool.' + tool
        enabled = parse_bool(val(section, 'enabled', 'true'), '[%s].enabled' % section, errors)
        override = val(section, 'profile_override', 'inherit')
        if override not in ('inherit',) + PROFILES:
            errors.append('[%s].profile_override must be inherit|quick|standard|deep' % section)
        tool_overrides[tool] = dict(enabled=enabled, profile_override=override)
    budgets = {}
    for key in sorted(LIMITS):
        budgets[key] = int_nonnegative(val('limits', key, '0'), '[limits].'+key, errors)
    schedules = {}
    for section in data.sections():
        if not section.startswith('schedule.') or not ID.fullmatch(section[9:]):
            continue
        job = section[9:]
        schedule_errors_before = len(errors)
        enabled = parse_bool(val(section, 'enabled', 'false'), '[%s].enabled' % section, errors)
        clock = val(section, 'time')
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', clock):
            errors.append('[%s].time must be 24-hour HH:MM' % section)
        days = parse_days(val(section, 'days'), '[%s].days' % section, errors)
        profile = val(section, 'profile')
        if profile not in PROFILES:
            errors.append('[%s].profile must be quick|standard|deep' % section)
        modules = parse_modules(val(section, 'modules'), '[%s].modules' % section, errors)
        if enabled:
            warnings.append('[%s].enabled=true is stored only; v0.1.0 will NOT create timers or run jobs' % section)
        if len(errors) == schedule_errors_before:
            schedules[job] = dict(enabled=enabled, time=clock, days=days, profile=profile, modules=modules)
    if errors:
        die('%s failed validation:\n - %s' % (source, '\n - '.join(errors)))
    return dict(config_version=1, server_id=sid, timezone=timezone_value,
                default_profile=default_profile, enable_heavy_tests=heavy,
                profiles=profiles, tools=tool_overrides, limits=budgets,
                schedules=schedules), warnings


def load(path):
    return validate_text(cm.safe_read(path), str(path))


def effective_profile(model, profile):
    if profile not in PROFILES:
        die('invalid profile: %s' % profile, EXIT_USAGE)
    result = {}
    for tool in TOOLS:
        override = model['tools'][tool]
        selected = profile if override['profile_override'] == 'inherit' else override['profile_override']
        mode = model['profiles'][selected][tool] if override['enabled'] else 'off'
        result[tool] = dict(mode=mode, effective_profile=selected, enabled=override['enabled'])
    return result


def atomic_update(path, candidate_text):
    validate_text(candidate_text, str(path))
    cm.ensure_private_parent(path)
    old = cm.safe_read(path)
    if old == candidate_text:
        return False
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix='.' + path.name + '.tmp-', dir=str(path.parent))
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            out.write(candidate_text)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temp_path, 0o600)
        validate_text(cm.safe_read(Path(temp_path)), temp_path)
        previous = path.read_bytes()
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = path.parent / ('.%s.backup-%s' % (path.name, stamp))
        old_fd = os.open(str(backup), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(old_fd, 'wb') as out:
            out.write(previous)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_path, path)
        temp_path = None
        return True
    except (OSError, UnicodeError) as exc:
        die('atomic S configuration update failed: %s' % exc, EXIT_FAILED)
    finally:
        if temp_path is not None:
            try: os.unlink(temp_path)
            except FileNotFoundError: pass


def edit(path, editor):
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        die('editing requires TTY; use --dry-run to preview', EXIT_USAGE)
    executable = cm.pick_editor(editor)
    with cm.locked(path):
        current = cm.safe_read(path)
        fd, candidate = tempfile.mkstemp(prefix='.' + path.name + '.edit-', dir=str(path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                out.write(current)
            os.chmod(candidate, 0o600)
            rc = subprocess.run([executable, candidate], check=False).returncode
            if rc:
                die('editor returned %d, original preserved' % rc, EXIT_FAILED)
            changed = cm.safe_read(Path(candidate))
            if changed == current:
                print('[NetworkLab] No changes: %s' % path)
                return
            new_model, _ = validate_text(changed, str(path))
            try:
                old_model, _ = validate_text(current, str(path))
            except cm.ConfigurationError:
                old_model = None  # Allow editor to repair an invalid existing file.
            if old_model and new_model['server_id'] != old_model['server_id']:
                print('[NetworkLab] WARNING: server_id changed; historical result identities will NOT be migrated', file=sys.stderr)
            if atomic_update(path, changed):
                print('[NetworkLab] Updated: %s' % path)
        finally:
            try: os.unlink(candidate)
            except FileNotFoundError: pass


def main(argv=None):
    a = argparse.ArgumentParser(description='NetworkLab B08 Server configuration manager')
    a.add_argument('--home', required=True)
    a.add_argument('--config', default='')
    a.add_argument('--action', choices=('validate', 'profiles', 'edit'), required=True)
    a.add_argument('--editor', default='nano')
    a.add_argument('--quiet', action='store_true')
    a.add_argument('--dry-run', action='store_true')
    args = a.parse_args(argv)
    try:
        home = Path(args.home)
        if not home.is_absolute():
            die('NETLAB_HOME must be absolute')
        path = Path(args.config).expanduser() if args.config else home / 'config' / 's.conf'
        if args.action in ('validate', 'profiles'):
            model, warnings = load(path)
        else:
            cm.safe_read(path)  # Editing may repair a currently invalid INI.
        if args.action == 'validate':
            if args.dry_run:
                die('config validate does not accept --dry-run', EXIT_USAGE)
            if not args.quiet:
                for w in warnings:
                    print('[NetworkLab] WARNING: '+w, file=sys.stderr)
            print('[NetworkLab] VALID s.conf: %s (server_id=%s, schedules=%d)' % (path, model['server_id'], len(model['schedules'])))
        elif args.action == 'profiles':
            for profile in PROFILES:
                print('[%s]%s' % (profile, ' (default)' if profile == model['default_profile'] else ''))
                for tool, entry in effective_profile(model, profile).items():
                    print('  %-17s %-6s  profile=%s%s' % (tool, entry['mode'], entry['effective_profile'], '' if entry['enabled'] else ' (disabled)'))
            print('[limits] run=%d MB, day=%d MB (0=no metered allowance)' % (
                model['limits']['max_metered_mb_per_run'],model['limits']['max_metered_mb_per_day']))
            print('[general] heavy_tests=%s; configured_schedule_jobs=%d (NOT ACTIVE in v0.1.0)' % (
                str(model['enable_heavy_tests']).lower(), len(model['schedules'])))
        elif args.action == 'edit':
            if args.dry_run:
                print('[NetworkLab] DRY_RUN editor %s %s' % (args.editor, path))
            else:
                edit(path, args.editor)
        return 0
    except cm.ConfigurationError as exc:
        names={EXIT_USAGE:'USAGE_ERROR',EXIT_CONFIG:'CONFIG_ERROR',EXIT_DEP:'DEPENDENCY_MISSING',EXIT_FAILED:'EXECUTION_FAILED',EXIT_SAFETY:'SAFETY_BLOCKED'}
        print('[NetworkLab] %s (%d): %s' % (names.get(exc.code,'ERROR'),exc.code,exc),file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        print('[NetworkLab] INTERRUPTED (130)', file=sys.stderr)
        return 130

if __name__ == '__main__':
    sys.exit(main())
