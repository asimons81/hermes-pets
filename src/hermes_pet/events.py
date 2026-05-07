"""Small local event schema for Hermes Pets ambient activity."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

EVENT_TYPES = {
    "bubble",
    "status",
    "job_started",
    "job_finished",
    "job_failed",
    "job_history",
    "approval_needed",
    "message_received",
    "daily_brief",
}

EVENT_SEVERITY = {
    "bubble": "info",
    "status": "info",
    "job_started": "info",
    "job_finished": "success",
    "job_failed": "error",
    "job_history": "info",
    "approval_needed": "warning",
    "message_received": "info",
    "daily_brief": "info",
}

EVENT_SCHEMA = "hermes.pet.event.v1"

URGENCY_VALUES = {
    "normal",
    "important",
    "urgent",
}

_TEXT_FIELD_LIMITS = {
    "source": 40,
    "source_id": 120,
    "sender": 120,
    "job_id": 120,
    "job_name": 120,
    "project_id": 120,
    "project_path": 260,
    "session_id": 120,
    "session_label": 120,
    "action_label": 120,
    "action_command": 260,
    "privacy_summary": 280,
}

_COMPAT_FIELDS = {
    "command",
    "duration_s",
    "exit_code",
    "schema",
    "sender",
    "urgent",
}

_PHASE4_FIELDS = {
    "source",
    "source_id",
    "urgency",
    "project_id",
    "project_path",
    "session_id",
    "session_label",
    "action_label",
    "action_command",
    "action_url",
    "privacy_summary",
}

_ALLOWED_EXTRA_FIELDS = _COMPAT_FIELDS | _PHASE4_FIELDS | {"job_id", "job_name"}


class PetEventError(ValueError):
    """Raised when an event cannot be represented by the v1 schema."""


def _clean_text(value: Any, *, field: str = "text") -> str:
    text = str(value or "").strip()
    if not text:
        raise PetEventError(f"{field} cannot be empty")
    return text[:500]


def _clean_optional_text(value: Any, *, field: str, limit: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:limit]


def _clean_urgency(value: Any) -> str:
    urgency = str(value or "normal").strip().lower().replace("-", "_")
    if urgency not in URGENCY_VALUES:
        allowed = ", ".join(sorted(URGENCY_VALUES))
        raise PetEventError(f"urgency must be one of: {allowed}")
    return urgency


def _clean_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _clean_int(value: Any, *, field: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise PetEventError(f"{field} must be an integer") from None


def _clean_duration(value: Any) -> float:
    try:
        return round(max(0.0, float(value)), 3)
    except (TypeError, ValueError):
        raise PetEventError("duration_s must be a number") from None


def _clean_action_url(value: Any) -> str | None:
    text = _clean_optional_text(value, field="action_url", limit=260)
    if text is None:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PetEventError("action_url must be an http or https URL")
    return text


def _clean_command(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    parts = [str(part).strip()[:120] for part in value[:20] if str(part).strip()]
    return parts or None


def _clean_extra_fields(extra: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in extra.items():
        if key not in _ALLOWED_EXTRA_FIELDS or value is None:
            continue
        if key == "schema":
            if value and str(value) != EVENT_SCHEMA:
                raise PetEventError(f"schema must be {EVENT_SCHEMA}")
            continue
        if key == "urgency":
            clean[key] = _clean_urgency(value)
        elif key == "urgent":
            clean[key] = _clean_bool(value)
        elif key == "exit_code":
            cleaned = _clean_int(value, field=key)
            if cleaned is not None:
                clean[key] = cleaned
        elif key == "duration_s":
            clean[key] = _clean_duration(value)
        elif key == "action_url":
            cleaned_url = _clean_action_url(value)
            if cleaned_url:
                clean[key] = cleaned_url
        elif key == "command":
            cleaned_command = _clean_command(value)
            if cleaned_command:
                clean[key] = cleaned_command
        else:
            limit = _TEXT_FIELD_LIMITS.get(key, 120)
            cleaned_text = _clean_optional_text(value, field=key, limit=limit)
            if cleaned_text:
                clean[key] = cleaned_text
    return clean


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_event(event_type: str, text: str, **extra: Any) -> dict[str, Any]:
    """Return a normalized v1 pet event.

    The renderer treats ``text`` as the human-facing summary and can use the
    optional fields for richer integrations later.
    """
    normalized_type = str(event_type or "").strip().lower().replace("-", "_")
    if normalized_type not in EVENT_TYPES:
        allowed = ", ".join(sorted(EVENT_TYPES))
        raise PetEventError(f"unknown event type {event_type!r}; expected one of: {allowed}")

    severity = str(extra.pop("severity", "") or EVENT_SEVERITY[normalized_type])[:40]
    event_id = str(extra.pop("id", "") or uuid4())[:120]
    created_at = str(extra.pop("created_at", "") or _utc_now_iso())[:40]
    clean_extra = _clean_extra_fields(extra)
    urgency = _clean_urgency(clean_extra.pop("urgency", "normal"))
    urgent = clean_extra.get("urgent")
    if urgent is True:
        urgency = "urgent"
    elif urgency == "urgent":
        clean_extra["urgent"] = True

    event: dict[str, Any] = {
        "type": normalized_type,
        "text": _clean_text(text),
        "severity": severity,
        "id": event_id,
        "created_at": created_at,
        "schema": EVENT_SCHEMA,
        "urgency": urgency,
    }

    if normalized_type == "message_received":
        clean_extra.setdefault("source", "telegram" if "telegram" in event["text"].lower() else "message")
        clean_extra.setdefault("sender", "")

    event.update(clean_extra)
    return event


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize trusted JSON-ish event data into the v1 schema when possible."""
    if not isinstance(event, dict):
        raise PetEventError("event must be a JSON object")
    event_type = str(event.get("type") or "")
    text = event.get("text") or event.get("message") or event.get("title")
    if not text and event_type == "message_received":
        sender = event.get("sender") or "someone"
        source = event.get("source") or "message"
        text = f"{source} from {sender}"
    extra = {key: value for key, value in event.items() if key not in {"type", "text", "message", "title"}}
    return build_event(event_type, str(text or ""), **extra)
