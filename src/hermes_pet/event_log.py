"""Bounded local event log for CLI-emitted Hermes Pets activity."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from hermes_pet.jobs import redact_text

EVENT_LOG_LIMIT = 200
EVENT_TEXT_LIMIT = 280

_SAFE_EVENT_KEYS = {
    "created_at",
    "duration_s",
    "exit_code",
    "id",
    "job_id",
    "job_name",
    "sender",
    "severity",
    "source",
    "text",
    "type",
    "urgent",
}


def _redact_and_truncate(value: object, *, limit: int) -> str:
    text = redact_text(str(value or ""), limit=max(limit * 4, 512))
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


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
        if key in {"text", "sender", "source", "job_name"}:
            limit = EVENT_TEXT_LIMIT if key == "text" else 96
            clean[key] = _redact_and_truncate(value, limit=limit)
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
    return [item for item in data if isinstance(item, dict)]


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
