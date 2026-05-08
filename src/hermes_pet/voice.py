"""Opt-in voice preview command adapter for Hermes Pets."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from hermes_pet.prefs import load_prefs


VOICE_EVENT_ALLOWLIST = {"message_received", "job_failed", "approval_needed", "voice_test"}
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_COMMAND_CHARS = 2048
MAX_VOICE_TEXT_CHARS = 500


def state_dir() -> Path:
    return Path(os.environ.get("HERMES_PET_HOME") or "~/.hermes_pet").expanduser()


def voice_prefs_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir).expanduser() if base_dir is not None else state_dir()
    return root / "voice-prefs.json"


def normalize_voice_prefs(raw: dict[str, Any] | None = None) -> dict[str, object]:
    raw = raw if isinstance(raw, dict) else {}
    enabled = bool(raw.get("enabled", False))
    command = str(raw.get("command") or "").strip()[:MAX_COMMAND_CHARS]
    try:
        timeout = float(raw.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS) or DEFAULT_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS
    return {
        "enabled": enabled,
        "command": command,
        "timeout_seconds": max(0.25, min(timeout, 30.0)),
    }


def load_voice_prefs(base_dir: str | Path | None = None) -> dict[str, object]:
    path = voice_prefs_path(base_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return normalize_voice_prefs()
    return normalize_voice_prefs(data if isinstance(data, dict) else None)


def save_voice_prefs(prefs: dict[str, object], base_dir: str | Path | None = None) -> dict[str, object]:
    clean = normalize_voice_prefs(prefs)
    path = voice_prefs_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return clean


def set_voice_enabled(enabled: bool, base_dir: str | Path | None = None) -> dict[str, object]:
    prefs = load_voice_prefs(base_dir)
    prefs["enabled"] = bool(enabled)
    return save_voice_prefs(prefs, base_dir)


def set_voice_command(command: str, base_dir: str | Path | None = None) -> dict[str, object]:
    prefs = load_voice_prefs(base_dir)
    prefs["command"] = str(command or "").strip()
    return save_voice_prefs(prefs, base_dir)


def configured_command(base_dir: str | Path | None = None) -> str:
    override = str(os.environ.get("HERMES_PET_TTS_COMMAND") or "").strip()[:MAX_COMMAND_CHARS]
    if override:
        return override
    return str(load_voice_prefs(base_dir).get("command") or "").strip()


def voice_status(base_dir: str | Path | None = None) -> dict[str, object]:
    prefs = load_voice_prefs(base_dir)
    override = str(os.environ.get("HERMES_PET_TTS_COMMAND") or "").strip()
    return {
        "enabled": bool(prefs.get("enabled")),
        "command": override or str(prefs.get("command") or ""),
        "command_source": "env" if override else "prefs",
        "timeout_seconds": prefs.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        "allowlist": sorted(VOICE_EVENT_ALLOWLIST),
    }


def _event_env(event: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    env["HERMES_PET_TTS_EVENT_TYPE"] = str(event.get("type") or "")
    env["HERMES_PET_TTS_SEVERITY"] = str(event.get("severity") or "")
    env["HERMES_PET_TTS_URGENCY"] = str(event.get("urgency") or ("urgent" if event.get("urgent") else "normal"))
    return env


def _event_text(event: dict[str, Any]) -> str:
    return str(event.get("text") or "").strip()[:MAX_VOICE_TEXT_CHARS]


def _os_error_reason(exc: OSError) -> str:
    if isinstance(exc, FileNotFoundError):
        return "command-not-found"
    if isinstance(exc, PermissionError):
        return "command-not-executable"
    return "command-unavailable"


def _is_suppressed_by_quiet_mode(base_dir: str | Path | None) -> bool:
    prefs = load_prefs(Path(base_dir).expanduser() if base_dir is not None else None)
    return str(prefs.get("quiet_mode") or "off") == "silent" or str(prefs.get("notification_profile") or "") == "silent"


def run_voice_for_event(
    event: dict[str, Any],
    *,
    base_dir: str | Path | None = None,
    explicit: bool = False,
) -> dict[str, object]:
    event_type = str(event.get("type") or "").strip()
    if event_type not in VOICE_EVENT_ALLOWLIST:
        return {"ok": True, "skipped": True, "reason": "event-not-allowlisted"}

    prefs = load_voice_prefs(base_dir)
    if not explicit and not bool(prefs.get("enabled")):
        return {"ok": True, "skipped": True, "reason": "voice-disabled"}
    if not explicit and _is_suppressed_by_quiet_mode(base_dir):
        return {"ok": True, "skipped": True, "reason": "quiet-mode-silent"}

    command_text = configured_command(base_dir)
    if not command_text:
        return {"ok": False, "skipped": True, "reason": "voice-command-missing"}
    try:
        command = shlex.split(command_text)
    except ValueError as exc:
        return {"ok": False, "skipped": True, "reason": f"invalid-command: {exc}"}
    if not command:
        return {"ok": False, "skipped": True, "reason": "voice-command-missing"}

    text = _event_text(event)
    timeout = float(prefs.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS) or DEFAULT_TIMEOUT_SECONDS)
    try:
        result = subprocess.run(
            command,
            input=text,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=_event_env(event),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "skipped": False, "reason": "timeout"}
    except OSError as exc:
        return {"ok": False, "skipped": False, "reason": _os_error_reason(exc)}

    ok = result.returncode == 0
    output_redacted = bool((result.stdout or "").strip() or (result.stderr or "").strip())
    return {
        "ok": ok,
        "skipped": False,
        "exit_code": int(result.returncode),
        "output_redacted": output_redacted,
        "reason": "" if ok else "command-failed",
    }


def run_voice_test(text: str, base_dir: str | Path | None = None) -> dict[str, object]:
    return run_voice_for_event(
        {"type": "voice_test", "text": text or "Hermes Pets voice preview test.", "urgency": "normal"},
        base_dir=base_dir,
        explicit=True,
    )
