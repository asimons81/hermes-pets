"""Local notification preferences for Hermes Pets."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

QUIET_MODES = {"off", "important", "silent"}
NOTIFICATION_PROFILES = {"normal", "focus", "pairing", "demo", "silent"}

NOTIFICATION_PROFILE_DEFAULTS: dict[str, dict[str, object]] = {
    "normal": {
        "quiet_mode": "off",
        "bubble_throttle_seconds": 2.5,
        "show_tray_on_urgent": True,
        "show_idle_bubbles": True,
    },
    "focus": {
        "quiet_mode": "important",
        "bubble_throttle_seconds": 8.0,
        "show_tray_on_urgent": True,
        "show_idle_bubbles": False,
    },
    "pairing": {
        "quiet_mode": "off",
        "bubble_throttle_seconds": 1.0,
        "show_tray_on_urgent": True,
        "show_idle_bubbles": True,
    },
    "demo": {
        "quiet_mode": "off",
        "bubble_throttle_seconds": 0.5,
        "show_tray_on_urgent": True,
        "show_idle_bubbles": False,
    },
    "silent": {
        "quiet_mode": "silent",
        "bubble_throttle_seconds": 30.0,
        "show_tray_on_urgent": False,
        "show_idle_bubbles": False,
    },
}

DEFAULT_PREFS: dict[str, object] = {
    "notification_profile": "normal",
    "muted_until": None,
    "quiet_mode": "off",
    "bubble_throttle_seconds": 2.5,
    "show_tray_on_urgent": True,
    "show_idle_bubbles": True,
}


def state_dir() -> Path:
    return Path(os.environ.get("HERMES_PET_HOME") or "~/.hermes_pet").expanduser()


def prefs_path(base_dir: Path | None = None) -> Path:
    return (base_dir or state_dir()) / "notification-prefs.json"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_notification_profile(value: object) -> str:
    profile = str(value or "normal").strip().lower().replace("-", "_")
    return profile if profile in NOTIFICATION_PROFILES else "normal"


def _profile_from_legacy_quiet_mode(raw: dict[str, Any] | None) -> str:
    if not raw or "notification_profile" in raw:
        return normalize_notification_profile((raw or {}).get("notification_profile"))
    quiet_mode = str(raw.get("quiet_mode") or "off").strip().lower()
    if quiet_mode == "silent":
        return "silent"
    if quiet_mode == "important":
        return "focus"
    return "normal"


def normalize_prefs(raw: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, object]:
    prefs = dict(DEFAULT_PREFS)
    profile = _profile_from_legacy_quiet_mode(raw)
    prefs.update(NOTIFICATION_PROFILE_DEFAULTS[profile])
    prefs["notification_profile"] = profile
    if raw:
        prefs.update({key: value for key, value in raw.items() if key in DEFAULT_PREFS})
        prefs["notification_profile"] = normalize_notification_profile(prefs.get("notification_profile"))

    quiet_mode = str(prefs.get("quiet_mode") or "off").strip().lower()
    prefs["quiet_mode"] = quiet_mode if quiet_mode in QUIET_MODES else "off"

    try:
        throttle = float(prefs.get("bubble_throttle_seconds") or DEFAULT_PREFS["bubble_throttle_seconds"])
    except (TypeError, ValueError):
        throttle = float(DEFAULT_PREFS["bubble_throttle_seconds"])
    prefs["bubble_throttle_seconds"] = max(0.0, min(throttle, 3600.0))

    prefs["show_tray_on_urgent"] = bool(prefs.get("show_tray_on_urgent"))
    prefs["show_idle_bubbles"] = bool(prefs.get("show_idle_bubbles"))

    current = now or utc_now()
    muted_until = parse_timestamp(prefs.get("muted_until"))
    prefs["muted_until"] = format_timestamp(muted_until) if muted_until and muted_until > current else None
    return prefs


def load_prefs(base_dir: Path | None = None) -> dict[str, object]:
    path = prefs_path(base_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return normalize_prefs()
    except (OSError, json.JSONDecodeError):
        return normalize_prefs()
    return normalize_prefs(raw if isinstance(raw, dict) else None)


def save_prefs(prefs: dict[str, object], base_dir: Path | None = None) -> dict[str, object]:
    clean = normalize_prefs(prefs)
    path = prefs_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return clean


def set_quiet_mode(mode: str, base_dir: Path | None = None) -> dict[str, object]:
    normalized = mode.strip().lower()
    if normalized not in QUIET_MODES:
        allowed = ", ".join(sorted(QUIET_MODES))
        raise ValueError(f"quiet_mode must be one of: {allowed}")
    prefs = load_prefs(base_dir)
    prefs["quiet_mode"] = normalized
    prefs["notification_profile"] = {"off": "normal", "important": "focus", "silent": "silent"}[normalized]
    if normalized == "off":
        prefs["muted_until"] = None
    return save_prefs(prefs, base_dir)


def apply_notification_profile(profile: str, base_dir: Path | None = None) -> dict[str, object]:
    normalized = normalize_notification_profile(profile)
    if normalized != str(profile or "").strip().lower().replace("-", "_"):
        allowed = ", ".join(sorted(NOTIFICATION_PROFILES))
        raise ValueError(f"notification profile must be one of: {allowed}")
    prefs = load_prefs(base_dir)
    prefs.update(NOTIFICATION_PROFILE_DEFAULTS[normalized])
    prefs["notification_profile"] = normalized
    if normalized != "silent":
        prefs["muted_until"] = None
    return save_prefs(prefs, base_dir)


def mute_for(duration: timedelta, base_dir: Path | None = None) -> dict[str, object]:
    if duration.total_seconds() <= 0:
        raise ValueError("mute duration must be greater than zero")
    prefs = load_prefs(base_dir)
    prefs["muted_until"] = format_timestamp(utc_now() + duration)
    return save_prefs(prefs, base_dir)
