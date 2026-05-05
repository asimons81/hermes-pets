"""Local notification preferences for Hermes Pets."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

QUIET_MODES = {"off", "important", "silent"}

DEFAULT_PREFS: dict[str, object] = {
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


def normalize_prefs(raw: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, object]:
    prefs = dict(DEFAULT_PREFS)
    if raw:
        prefs.update({key: value for key, value in raw.items() if key in DEFAULT_PREFS})

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
    if normalized == "off":
        prefs["muted_until"] = None
    return save_prefs(prefs, base_dir)


def mute_for(duration: timedelta, base_dir: Path | None = None) -> dict[str, object]:
    if duration.total_seconds() <= 0:
        raise ValueError("mute duration must be greater than zero")
    prefs = load_prefs(base_dir)
    prefs["muted_until"] = format_timestamp(utc_now() + duration)
    return save_prefs(prefs, base_dir)
