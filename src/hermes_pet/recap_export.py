"""Local recap-card export bundle writer for Hermes Pets.

This module turns the local pet state, recent jobs, and safe events into a
share-friendly bundle containing:
- recap-card.png
- caption.txt
- metadata.json

The renderer is treated as a black box with a narrow contract. The export layer
only assembles sanitized payloads and writes local files.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from hermes_pet.custom_pets import current_custom_pet
from hermes_pet.engine import CUSTOM_PET_SPECIES, SPECIES, load_pet
from hermes_pet.event_log import load_events, safe_event
from hermes_pet.jobs import job_scan_summary, recent_jobs, redact_text
from hermes_pet.prefs import load_prefs
from hermes_pet.update import current_version

try:  # pragma: no cover - exercised indirectly when the sibling renderer lands
    from hermes_pet.recap_card import render_recap_card  # pyright: ignore[reportMissingImports]
except Exception:  # pragma: no cover - import fallback for this worktree
    def render_recap_card(payload: dict[str, Any], output_path: Path) -> Path:
        raise RecapExportError(
            "Recap card renderer is unavailable. Merge the recap-card worktree first."
        )


class RecapExportError(RuntimeError):
    """Raised when the recap export bundle cannot be built safely."""


_PATH_REPLACEMENTS = (
    # WSL / Linux style absolute paths.
    re.compile(r"(?<!\w)/[^\s\"'`<>{}\[\]()/]+(?:/[^\s\"'`<>{}\[\]()/]+)*"),

    re.compile(r"(?<!\w)[A-Za-z]:\\[^\s\"'`<>{}\[\]()]+"),
)


def _state_dir() -> Path:
    return Path(os.environ.get("HERMES_PET_HOME") or "~/.hermes_pet").expanduser()


def _parse_since_duration(value: str) -> timedelta:
    text = str(value or "").strip().lower()
    if len(text) < 2:
        raise RecapExportError("since must look like 30m, 2h, 24h, or 7d")
    suffix = text[-1]
    units = {"m": 60, "h": 3600, "d": 86400}
    if suffix not in units:
        raise RecapExportError("since must use m, h, or d, such as 30m, 2h, 24h, or 7d")
    try:
        amount = int(text[:-1])
    except ValueError as exc:
        raise RecapExportError("since must start with a whole number") from exc
    if amount <= 0:
        raise RecapExportError("since must be greater than zero")
    return timedelta(seconds=amount * units[suffix])


def _parse_iso_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _within_since(item: dict[str, object], cutoff: datetime) -> bool:
    for key in ("created_at", "finished_at", "started_at"):
        parsed = _parse_iso_time(item.get(key))
        if parsed is not None:
            return parsed >= cutoff
    return False


def _item_time(item: dict[str, object]) -> datetime:
    for key in ("created_at", "finished_at", "started_at"):
        parsed = _parse_iso_time(item.get(key))
        if parsed is not None:
            return parsed
    return datetime.min.replace(tzinfo=timezone.utc)


def _timestamp_slug(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _single_line(text: object) -> str:
    return " ".join(str(text or "").split())


def _redact_paths(text: str) -> str:
    redacted = text
    for pattern in _PATH_REPLACEMENTS:
        redacted = pattern.sub("[local path]", redacted)
    return redacted


def _sanitize_share_text(value: object, *, limit: int = 280) -> str:
    text = redact_text(_single_line(value), limit=max(limit * 4, 512))
    text = _redact_paths(text)
    text = _single_line(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _sanitize_share_lines(values: Sequence[object], *, limit: int = 180) -> list[str]:
    return [line for line in (_sanitize_share_text(value, limit=limit) for value in values) if line]


def _pet_identity(pet: Any | None, custom_pet: dict[str, Any] | None) -> dict[str, Any]:
    if pet is None:
        return {
            "name_or_label": "Hermes Pet",
            "species": "unknown",
            "level": 0,
            "rarity": "unknown",
        }

    species = str(getattr(pet, "species", "") or "").strip().lower()
    custom_name = str((custom_pet or {}).get("name") or "").strip()
    if species == CUSTOM_PET_SPECIES:
        name_or_label = _sanitize_share_text(custom_name or getattr(pet, "name", "Custom pet"), limit=40) or "Custom pet"
        rarity = "custom"
    else:
        name = _sanitize_share_text(getattr(pet, "name", ""), limit=40)
        name_or_label = name or species.title() or "Hermes Pet"
        rarity = SPECIES[species].rarity if species in SPECIES else "unknown"

    return {
        "name_or_label": name_or_label,
        "species": species or "unknown",
        "level": int(getattr(pet, "level", 0) or 0),
        "rarity": rarity,
    }


def _success_streak(jobs: list[dict[str, Any]]) -> int:
    streak = 0
    for job in jobs:
        status = str(job.get("status") or "").strip().lower()
        exit_code = job.get("exit_code")
        if status == "succeeded" or exit_code == 0:
            streak += 1
        else:
            break
    return streak


def _pick_dominant_moment(
    events: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
) -> dict[str, str]:
    urgent_events = [
        event
        for event in events
        if str(event.get("type") or "") == "approval_needed"
        or bool(event.get("urgent"))
        or str(event.get("urgency") or "").strip().lower() == "urgent"
    ]
    if urgent_events:
        event = urgent_events[0]
        return {
            "type": "approval_needed",
            "headline": _sanitize_share_text(event.get("text") or "approval needed", limit=80) or "approval needed",
            "safe_summary": _sanitize_share_text(event.get("text") or "approval needed", limit=160) or "approval needed",
        }

    failed_jobs = [
        job
        for job in jobs
        if str(job.get("status") or "").strip().lower() == "failed"
        or job.get("exit_code") not in (None, 0)
    ]
    if failed_jobs:
        job = failed_jobs[0]
        job_name = _sanitize_share_text(job.get("name") or "job", limit=60) or "job"
        detail = _sanitize_share_text(job.get("error_summary") or job.get("output_summary") or "", limit=120)
        safe_summary = f"{job_name} failed"
        if detail:
            safe_summary = f"{safe_summary}: {detail}"
        return {
            "type": "job_failed",
            "headline": safe_summary,
            "safe_summary": safe_summary,
        }

    streak = _success_streak(jobs)
    if streak:
        job = jobs[0]
        job_name = _sanitize_share_text(job.get("name") or "job", limit=60) or "job"
        if streak > 1:
            headline = f"{streak} successful jobs in a row"
        else:
            headline = f"{job_name} finished cleanly"
        return {
            "type": "job_succeeded",
            "headline": headline,
            "safe_summary": headline,
        }

    lifecycle_events = [
        event
        for event in events
        if str(event.get("type") or "") in {"status", "job_started", "job_finished", "job_history"}
    ]
    if lifecycle_events:
        event = lifecycle_events[0]
        text = _sanitize_share_text(event.get("text") or event.get("type") or "lifecycle event", limit=120)
        return {
            "type": str(event.get("type") or "job_history"),
            "headline": text,
            "safe_summary": text,
        }

    message_events = [event for event in events if str(event.get("type") or "") == "message_received"]
    if message_events:
        event = message_events[0]
        source = _sanitize_share_text(event.get("source") or "message", limit=40) or "message"
        sender = _sanitize_share_text(event.get("sender") or "someone", limit=40) or "someone"
        headline = f"{source} from {sender}"
        return {
            "type": "message_received",
            "headline": headline,
            "safe_summary": headline,
        }

    headline = "quiet local session recap"
    return {
        "type": "fallback",
        "headline": headline,
        "safe_summary": headline,
    }


def _build_proof_points(
    *,
    jobs: list[dict[str, Any]],
    events: list[dict[str, Any]],
    dominant_moment: dict[str, str],
) -> list[str]:
    points: list[str] = []
    counts = job_scan_summary(jobs)
    points.append(
        _sanitize_share_text(
            f"{counts['succeeded']} successful jobs, {counts['failed']} failed, {counts['total']} total",
            limit=120,
        )
    )

    latest_success = next(
        (
            job
            for job in jobs
            if str(job.get("status") or "").strip().lower() == "succeeded" or job.get("exit_code") == 0
        ),
        None,
    )
    if latest_success is not None:
        name = _sanitize_share_text(latest_success.get("name") or "job", limit=50) or "job"
        summary = _sanitize_share_text(latest_success.get("output_summary") or "", limit=80)
        point = f"Latest success: {name}"
        if summary:
            point = f"{point} - {summary}"
        points.append(point)
    else:
        latest_event = events[0] if events else None
        if latest_event is not None:
            point = _sanitize_share_text(latest_event.get("text") or dominant_moment["safe_summary"], limit=120)
            if point:
                points.append(f"Latest event: {point}")

    if len(points) > 2:
        points = points[:2]
    return [point for point in _sanitize_share_lines(points, limit=120) if point]


def _collect_local_state(*, since: str, state_dir: Path, now: datetime) -> dict[str, Any]:
    cutoff = now - _parse_since_duration(since)
    jobs = [job for job in recent_jobs(base_dir=state_dir, newest_first=True) if _within_since(job, cutoff)]
    events = [safe_event(event) for event in reversed(load_events(state_dir)) if _within_since(event, cutoff)]
    pet = load_pet("", state_dir=state_dir)
    custom_pet = current_custom_pet(state_dir)
    dominant_moment = _pick_dominant_moment(events, jobs)
    proof_points = _build_proof_points(jobs=jobs, events=events, dominant_moment=dominant_moment)
    identity = _pet_identity(pet, custom_pet)
    if custom_pet and identity["species"] == CUSTOM_PET_SPECIES:
        identity["custom_pet"] = {"name": _sanitize_share_text(custom_pet.get("name") or "", limit=50) or "custom"}

    caption_parts = [
        f"{identity['name_or_label']} recap: {dominant_moment['headline']}."
    ]
    if proof_points:
        caption_parts.append(proof_points[0].rstrip("."))
    caption_parts.append("Local recap, not posted by Hermes Pets.")
    caption = _sanitize_share_text(" ".join(caption_parts), limit=280)
    footer = "Local recap, not posted by Hermes Pets"
    redaction_notes = [
        "absolute local paths were stripped from share text",
        "secret-like substrings were redacted from jobs and events",
    ]
    return {
        "state_dir": state_dir,
        "cutoff": cutoff,
        "jobs": jobs,
        "events": events,
        "pet": identity,
        "dominant_moment": dominant_moment,
        "proof_points": proof_points,
        "caption": caption,
        "footer": footer,
        "redaction": {"applied": True, "notes": redaction_notes},
        "source_window": {
            "since": since,
            "lookback_seconds": int(_parse_since_duration(since).total_seconds()),
        },
        "counts": {
            "jobs_total": len(jobs),
            "jobs_succeeded": sum(
                1
                for job in jobs
                if str(job.get("status") or "").strip().lower() == "succeeded" or job.get("exit_code") == 0
            ),
            "jobs_failed": sum(
                1
                for job in jobs
                if str(job.get("status") or "").strip().lower() == "failed" or job.get("exit_code") not in (None, 0)
            ),
            "events_total": len(events),
        },
    }


def build_recap_payload(*, since: str = "24h", state_dir: str | Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Return the sanitized payload passed into the recap card renderer."""
    root = Path(state_dir).expanduser() if state_dir is not None else _state_dir()
    actual_now = now or datetime.now(timezone.utc)
    context = _collect_local_state(since=since, state_dir=root, now=actual_now)
    payload = {
        "pet": context["pet"],
        "dominant_moment": context["dominant_moment"],
        "proof_points": context["proof_points"],
        "caption": context["caption"],
        "footer": context["footer"],
        "source_window": context["source_window"],
        "generated_at": actual_now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "counts": context["counts"],
        "redaction": context["redaction"],
    }
    if context["pet"].get("custom_pet"):
        payload["custom_pet"] = context["pet"]["custom_pet"]
    return payload


def resolve_output_dir(
    output_dir: str | Path | None,
    *,
    state_dir: str | Path | None = None,
    now: datetime | None = None,
) -> Path:
    root = Path(state_dir).expanduser() if state_dir is not None else _state_dir()
    actual_now = now or datetime.now(timezone.utc)
    if output_dir:
        bundle_dir = Path(output_dir).expanduser()
        if not bundle_dir.is_absolute():
            bundle_dir = bundle_dir.resolve()
        return bundle_dir
    return (root / "exports" / "recaps" / _timestamp_slug(actual_now)).resolve()


def _build_metadata(context: dict[str, Any], *, since: str, generated_at: datetime) -> dict[str, Any]:
    return {
        "schema": "hermes.pet.recap_bundle.v1",
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "generator_version": current_version(),
        "source_window": context["source_window"],
        "bundle_files": {
            "recap-card.png": {"path": "recap-card.png", "format": "PNG"},
            "caption.txt": {"path": "caption.txt", "format": "UTF-8 text"},
            "metadata.json": {"path": "metadata.json", "format": "JSON"},
        },
        "pet": {
            "name_or_label": context["pet"]["name_or_label"],
            "species": context["pet"]["species"],
            "level": context["pet"]["level"],
            "rarity": context["pet"]["rarity"],
        },
        "dominant_moment": {
            "type": context["dominant_moment"]["type"],
            "safe_summary": context["dominant_moment"]["safe_summary"],
        },
        "proof_points": context["proof_points"],
        "counts": context["counts"],
        "caption": context["caption"],
        "redaction": context["redaction"],
    }


def write_recap_bundle(
    *,
    since: str = "24h",
    output_dir: str | Path | None = None,
    state_dir: str | Path | None = None,
    now: datetime | None = None,
    renderer: Callable[[dict[str, Any], Path], Path | None] | None = None,
) -> Path:
    """Render a recap card and write the local export bundle."""
    root = Path(state_dir).expanduser() if state_dir is not None else _state_dir()
    actual_now = now or datetime.now(timezone.utc)
    context = _collect_local_state(since=since, state_dir=root, now=actual_now)
    payload = build_recap_payload(since=since, state_dir=root, now=actual_now)
    bundle_dir = resolve_output_dir(output_dir, state_dir=root, now=actual_now)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    image_path = bundle_dir / "recap-card.png"
    render = renderer or render_recap_card
    result = render(payload, image_path)
    if isinstance(result, Path):
        image_path = result
    elif result is not None:
        image_path = Path(result)

    caption_path = bundle_dir / "caption.txt"
    caption_path.write_text(payload["caption"] + "\n", encoding="utf-8")

    metadata = _build_metadata(context, since=since, generated_at=actual_now)
    metadata_path = bundle_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return bundle_dir


export_recap_bundle = write_recap_bundle
