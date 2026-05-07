"""Bounded local event log for CLI-emitted Hermes Pets activity."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from hermes_pet.events import EVENT_SCHEMA, URGENCY_VALUES
from hermes_pet.jobs import redact_command, redact_text

EVENT_LOG_LIMIT = 200
EVENT_TEXT_LIMIT = 280

_SAFE_EVENT_KEYS = {
    "action_command",
    "action_label",
    "action_url",
    "created_at",
    "duration_s",
    "exit_code",
    "id",
    "job_id",
    "job_name",
    "privacy_summary",
    "project_id",
    "project_path",
    "schema",
    "sender",
    "severity",
    "session_id",
    "session_label",
    "source",
    "source_id",
    "text",
    "type",
    "urgency",
    "urgent",
}

_TEXT_LIMITS = {
    "action_command": 260,
    "action_label": 120,
    "action_url": 260,
    "job_id": 120,
    "job_name": 96,
    "privacy_summary": 280,
    "project_id": 120,
    "project_path": 260,
    "sender": 96,
    "session_id": 120,
    "session_label": 120,
    "source": 96,
    "source_id": 120,
    "text": EVENT_TEXT_LIMIT,
}


def _redact_and_truncate(value: object, *, limit: int) -> str:
    text = redact_text(str(value or ""), limit=max(limit * 4, 512))
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _redact_action_command(value: object, *, limit: int) -> str:
    text = _redact_and_truncate(value, limit=max(limit * 4, 512))
    try:
        parts = shlex.split(text)
    except ValueError:
        parts = []
    if parts:
        redacted_parts, _ = redact_command(parts)
        text = " ".join(redacted_parts)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _clean_action_url(value: object, *, limit: int) -> str:
    text = _redact_and_truncate(value, limit=limit)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return text


def state_dir() -> Path:
    return Path(os.environ.get("HERMES_PET_HOME") or "~/.hermes_pet").expanduser()


def events_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir).expanduser() if base_dir is not None else state_dir()
    return root / "events.json"


def _clean_event(event: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key in _SAFE_EVENT_KEYS:
        if key not in event or event[key] is None:
            continue
        value = event[key]
        if key == "action_command":
            clean[key] = _redact_action_command(value, limit=_TEXT_LIMITS[key])
        elif key == "action_url":
            cleaned_url = _clean_action_url(value, limit=_TEXT_LIMITS[key])
            if cleaned_url:
                clean[key] = cleaned_url
        elif key in _TEXT_LIMITS:
            limit = _TEXT_LIMITS[key]
            clean[key] = _redact_and_truncate(value, limit=limit)
        elif key == "schema":
            if str(value) == EVENT_SCHEMA:
                clean[key] = EVENT_SCHEMA
        elif key == "urgency":
            urgency = str(value or "").strip().lower().replace("-", "_")
            if urgency in URGENCY_VALUES:
                clean[key] = urgency
        elif key in {"urgent"}:
            clean[key] = bool(value)
        elif key in {"exit_code"}:
            try:
                clean[key] = int(value)
            except (TypeError, ValueError):
                continue
        elif key in {"duration_s"}:
            try:
                clean[key] = round(max(0.0, float(value)), 3)
            except (TypeError, ValueError):
                continue
        else:
            clean[key] = str(value)[:120]
    return clean


def safe_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return the privacy-safe event payload used for storage and broadcast."""
    return _clean_event(event)


def load_events(base_dir: str | Path | None = None) -> list[dict[str, Any]]:
    path = events_path(base_dir)
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [_clean_event(item) for item in data if isinstance(item, dict)]


def save_events(events: list[dict[str, Any]], base_dir: str | Path | None = None) -> None:
    path = events_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    bounded = [_clean_event(event) for event in events if isinstance(event, dict)][-EVENT_LOG_LIMIT:]
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(bounded, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    tmp_path.replace(path)


def append_event(event: dict[str, Any], base_dir: str | Path | None = None) -> None:
    events = load_events(base_dir)
    events.append(_clean_event(event))
    save_events(events, base_dir)


def compact_events(*, base_dir: str | Path | None = None, keep: int = EVENT_LOG_LIMIT) -> dict[str, int]:
    events = load_events(base_dir)
    keep = max(0, min(int(keep), EVENT_LOG_LIMIT))
    kept = events[-keep:] if keep else []
    save_events(kept, base_dir)
    return {"before": len(events), "after": len(kept), "removed": max(0, len(events) - len(kept))}
