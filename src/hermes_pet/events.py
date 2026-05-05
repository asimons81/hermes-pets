"""Small local event schema for Hermes Pets ambient activity."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
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


class PetEventError(ValueError):
    """Raised when an event cannot be represented by the v1 schema."""


def _clean_text(value: Any, *, field: str = "text") -> str:
    text = str(value or "").strip()
    if not text:
        raise PetEventError(f"{field} cannot be empty")
    return text[:500]


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

    event: dict[str, Any] = {
        "type": normalized_type,
        "text": _clean_text(text),
        "severity": str(extra.pop("severity", "") or EVENT_SEVERITY[normalized_type]),
        "id": str(extra.pop("id", "") or uuid4()),
        "created_at": str(extra.pop("created_at", "") or _utc_now_iso()),
        "schema": "hermes.pet.event.v1",
    }

    if normalized_type == "message_received":
        event.setdefault("source", "telegram" if "telegram" in event["text"].lower() else "message")
        event.setdefault("sender", "")

    for key, value in extra.items():
        if value is not None:
            event[key] = value
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
