"""Foundational local achievements for Hermes Pets."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_pet.custom_pets import current_custom_pet, list_custom_pets
from hermes_pet.engine import load_pet
from hermes_pet.jobs import load_jobs
from hermes_pet.prefs import load_prefs, prefs_path
from hermes_pet.voice import load_voice_prefs


ACHIEVEMENT_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "first_custom_pet_imported",
        "title": "First Import",
        "description": "Imported a custom pet package.",
        "category": "Customization",
        "icon": "I",
        "tier": "Bronze",
        "accent": "secondary",
        "locked_hint": "Import a validated local custom pet package.",
        "sort_order": 10,
    },
    {
        "id": "first_custom_pet_selected",
        "title": "Operator's Choice",
        "description": "Selected an installed custom pet.",
        "category": "Customization",
        "icon": "C",
        "tier": "Bronze",
        "accent": "secondary",
        "locked_hint": "Select one installed custom pet for the overlay.",
        "sort_order": 20,
    },
    {
        "id": "first_wrapped_job_completed",
        "title": "Clean Run",
        "description": "Completed the first wrapped job.",
        "category": "Jobs",
        "icon": "OK",
        "tier": "Bronze",
        "accent": "success",
        "locked_hint": "Complete one wrapped command successfully.",
        "sort_order": 100,
    },
    {
        "id": "first_failed_job_recorded",
        "title": "Signal Captured",
        "description": "Recorded the first failed wrapped job.",
        "category": "Recovery",
        "icon": "!",
        "tier": "Bronze",
        "accent": "danger",
        "locked_hint": "Record one failed wrapped command.",
        "sort_order": 200,
    },
    {
        "id": "first_retryable_failure",
        "title": "Retry Ready",
        "description": "Captured a retryable failure.",
        "category": "Recovery",
        "icon": "R",
        "tier": "Bronze",
        "accent": "warning",
        "locked_hint": "Capture a failed wrapped command that can be retried.",
        "sort_order": 210,
    },
    {
        "id": "level_5",
        "title": "Level 5",
        "description": "Reached pet level 5.",
        "category": "Milestones",
        "icon": "5",
        "tier": "Bronze",
        "accent": "primary",
        "locked_hint": "Help your pet reach level 5.",
        "sort_order": 300,
    },
    {
        "id": "level_10",
        "title": "Level 10",
        "description": "Reached pet level 10.",
        "category": "Milestones",
        "icon": "10",
        "tier": "Silver",
        "accent": "primary",
        "locked_hint": "Help your pet reach level 10.",
        "sort_order": 310,
    },
    {
        "id": "first_dashboard_opened",
        "title": "Dashboard Check-In",
        "description": "Opened the local dashboard.",
        "category": "Operator Habits",
        "icon": "D",
        "tier": "Bronze",
        "accent": "primary",
        "locked_hint": "Open the token-gated local dashboard.",
        "sort_order": 400,
    },
    {
        "id": "first_test_event_sent",
        "title": "Signal Ping",
        "description": "Sent a dashboard test event to the overlay.",
        "category": "Operator Habits",
        "icon": "P",
        "tier": "Bronze",
        "accent": "primary",
        "locked_hint": "Use the dashboard Ping command.",
        "sort_order": 410,
    },
    {
        "id": "prefs_saved",
        "title": "Preferences Saved",
        "description": "Saved notification preferences locally.",
        "category": "Operator Habits",
        "icon": "S",
        "tier": "Bronze",
        "accent": "secondary",
        "locked_hint": "Save notification preferences from the dashboard or CLI.",
        "sort_order": 420,
    },
    {
        "id": "quiet_mode_enabled",
        "title": "Quiet Console",
        "description": "Enabled a quieter notification mode.",
        "category": "Operator Habits",
        "icon": "Q",
        "tier": "Bronze",
        "accent": "warning",
        "locked_hint": "Set quiet mode to important or silent.",
        "sort_order": 430,
    },
    {
        "id": "voice_preview_enabled",
        "title": "Voice Preview Armed",
        "description": "Enabled the local voice preview adapter.",
        "category": "Companion",
        "icon": "V",
        "tier": "Bronze",
        "accent": "secondary",
        "locked_hint": "Enable voice preview locally.",
        "sort_order": 500,
    },
    {
        "id": "voice_test_ran",
        "title": "Voice Test",
        "description": "Ran an explicit local voice preview test.",
        "category": "Companion",
        "icon": "T",
        "tier": "Bronze",
        "accent": "secondary",
        "locked_hint": "Run one explicit voice preview test.",
        "sort_order": 510,
    },
    {
        "id": "first_builtin_pet_change",
        "title": "Fresh Companion",
        "description": "Changed to a built-in pet from the dashboard.",
        "category": "Companion",
        "icon": "B",
        "tier": "Bronze",
        "accent": "warmth",
        "locked_hint": "Adopt or hatch a built-in pet from the dashboard.",
        "sort_order": 520,
    },
    {
        "id": "custom_pet_cleared",
        "title": "Built-In Restored",
        "description": "Cleared a custom visual without deleting the package.",
        "category": "Customization",
        "icon": "X",
        "tier": "Bronze",
        "accent": "secondary",
        "locked_hint": "Clear the current custom visual selection.",
        "sort_order": 30,
    },
    {
        "id": "three_jobs_completed",
        "title": "Three Clean Runs",
        "description": "Completed three wrapped jobs.",
        "category": "Jobs",
        "icon": "3",
        "tier": "Silver",
        "accent": "success",
        "locked_hint": "Complete three wrapped commands successfully.",
        "sort_order": 110,
    },
    {
        "id": "ten_jobs_completed",
        "title": "Ten Clean Runs",
        "description": "Completed ten wrapped jobs.",
        "category": "Jobs",
        "icon": "10",
        "tier": "Gold",
        "accent": "success",
        "locked_hint": "Complete ten wrapped commands successfully.",
        "sort_order": 120,
    },
    {
        "id": "failure_then_success",
        "title": "Recovered Run",
        "description": "Recorded a failure followed by a successful wrapped job.",
        "category": "Recovery",
        "icon": "RS",
        "tier": "Silver",
        "accent": "warning",
        "locked_hint": "Recover from a failed wrapped command with a later success.",
        "sort_order": 220,
    },
    {
        "id": "custom_pet_collection_3",
        "title": "Tiny Collection",
        "description": "Installed three valid custom pet packages.",
        "category": "Customization",
        "icon": "3",
        "tier": "Silver",
        "accent": "secondary",
        "locked_hint": "Keep three valid custom pet packages installed.",
        "sort_order": 40,
    },
    {
        "id": "level_15",
        "title": "Level 15",
        "description": "Reached pet level 15.",
        "category": "Milestones",
        "icon": "15",
        "tier": "Silver",
        "accent": "primary",
        "locked_hint": "Help your pet reach level 15.",
        "sort_order": 320,
    },
    {
        "id": "level_25",
        "title": "Level 25",
        "description": "Reached pet level 25.",
        "category": "Milestones",
        "icon": "25",
        "tier": "Gold",
        "accent": "warmth",
        "locked_hint": "Help your pet reach level 25.",
        "sort_order": 330,
    },
)

_DEFINITIONS_BY_ID = {item["id"]: item for item in ACHIEVEMENT_DEFINITIONS}


def state_dir() -> Path:
    return Path(os.environ.get("HERMES_PET_HOME") or "~/.hermes_pet").expanduser()


def achievements_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir).expanduser() if base_dir is not None else state_dir()
    return root / "achievements.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_achievement_state(base_dir: str | Path | None = None) -> dict[str, Any]:
    path = achievements_path(base_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"unlocked": {}}
    if not isinstance(data, dict):
        return {"unlocked": {}}
    unlocked = data.get("unlocked")
    if not isinstance(unlocked, dict):
        unlocked = {}
    clean = {}
    for achievement_id, item in unlocked.items():
        if achievement_id not in _DEFINITIONS_BY_ID or not isinstance(item, dict):
            continue
        clean[achievement_id] = {
            "unlocked_at": str(item.get("unlocked_at") or ""),
            "source": str(item.get("source") or ""),
        }
    return {"unlocked": clean}


def save_achievement_state(state: dict[str, Any], base_dir: str | Path | None = None) -> dict[str, Any]:
    clean = load_achievement_state(base_dir)
    incoming = state.get("unlocked") if isinstance(state, dict) else {}
    if isinstance(incoming, dict):
        for key, value in incoming.items():
            if key not in _DEFINITIONS_BY_ID or not isinstance(value, dict):
                continue
            clean["unlocked"][key] = {
                "unlocked_at": str(value.get("unlocked_at") or ""),
                "source": str(value.get("source") or ""),
            }
    path = achievements_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return clean


def unlock_achievement(
    achievement_id: str,
    *,
    base_dir: str | Path | None = None,
    source: str = "",
) -> dict[str, Any] | None:
    if achievement_id not in _DEFINITIONS_BY_ID:
        raise ValueError(f"unknown achievement: {achievement_id}")
    state = load_achievement_state(base_dir)
    if achievement_id in state["unlocked"]:
        return None
    state["unlocked"][achievement_id] = {
        "unlocked_at": utc_now_iso(),
        "source": str(source or ""),
    }
    save_achievement_state(state, base_dir)
    return achievement_status(base_dir, achievement_id)


def achievement_status(base_dir: str | Path | None = None, achievement_id: str | None = None) -> dict[str, Any]:
    state = load_achievement_state(base_dir)
    unlocked = state["unlocked"]
    if achievement_id:
        definition = _DEFINITIONS_BY_ID[achievement_id]
        item = dict(definition)
        item["unlocked"] = achievement_id in unlocked
        item.update(unlocked.get(achievement_id, {}))
        return item
    items = []
    for definition in ACHIEVEMENT_DEFINITIONS:
        item = dict(definition)
        item["unlocked"] = item["id"] in unlocked
        item.update(unlocked.get(item["id"], {}))
        items.append(item)
    return {
        "items": items,
        "unlocked_count": sum(1 for item in items if item["unlocked"]),
        "total_count": len(items),
    }


def sync_achievements(base_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Unlock achievements implied by existing local state."""
    unlocked: list[dict[str, Any]] = []

    def add(achievement_id: str, source: str) -> None:
        item = unlock_achievement(achievement_id, base_dir=base_dir, source=source)
        if item:
            unlocked.append(item)

    pets = list_custom_pets(Path(base_dir).expanduser() if base_dir is not None else None)
    if pets:
        add("first_custom_pet_imported", "state-scan")
    if current_custom_pet(Path(base_dir).expanduser() if base_dir is not None else None):
        add("first_custom_pet_selected", "state-scan")

    jobs = load_jobs(base_dir)
    succeeded_jobs = [job for job in jobs if job.get("status") == "succeeded" or job.get("exit_code") == 0]
    if succeeded_jobs:
        add("first_wrapped_job_completed", "state-scan")
    if len(succeeded_jobs) >= 3:
        add("three_jobs_completed", "state-scan")
    if len(succeeded_jobs) >= 10:
        add("ten_jobs_completed", "state-scan")
    failed_jobs = [job for job in jobs if job.get("status") == "failed" or job.get("exit_code") not in (0, None)]
    if failed_jobs:
        add("first_failed_job_recorded", "state-scan")
    if any(job.get("retryable") is not False and not job.get("command_redacted") for job in failed_jobs):
        add("first_retryable_failure", "state-scan")
    saw_failure = False
    for job in jobs:
        failed = job.get("status") == "failed" or job.get("exit_code") not in (0, None)
        succeeded = job.get("status") == "succeeded" or job.get("exit_code") == 0
        if saw_failure and succeeded:
            add("failure_then_success", "state-scan")
            break
        if failed:
            saw_failure = True

    pet = load_pet("", state_dir=base_dir)
    if pet and pet.level >= 5:
        add("level_5", "state-scan")
    if pet and pet.level >= 10:
        add("level_10", "state-scan")
    if pet and pet.level >= 15:
        add("level_15", "state-scan")
    if pet and pet.level >= 25:
        add("level_25", "state-scan")

    valid_pets = [pet for pet in pets if pet.get("valid")]
    if len(valid_pets) >= 3:
        add("custom_pet_collection_3", "state-scan")

    root = Path(base_dir).expanduser() if base_dir is not None else state_dir()
    prefs = load_prefs(root)
    if prefs_path(root).exists():
        add("prefs_saved", "state-scan")
    if prefs.get("quiet_mode") in {"important", "silent"}:
        add("quiet_mode_enabled", "state-scan")

    voice = load_voice_prefs(root)
    if voice.get("enabled"):
        add("voice_preview_enabled", "state-scan")

    return unlocked
