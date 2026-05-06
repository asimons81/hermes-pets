"""Recent wrapped-job history for Hermes Pets."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

HISTORY_LIMIT = 100
OUTPUT_SUMMARY_LIMIT = 600

_SENSITIVE_FLAG_NAMES = {
    "--api-key",
    "--apikey",
    "--auth",
    "--authorization",
    "--client-secret",
    "--key",
    "--password",
    "--passwd",
    "--secret",
    "--token",
}

_SENSITIVE_KEY_RE = re.compile(
    r"(?i)\b("
    r"api[_-]?key|authorization|auth[_-]?token|bearer|client[_-]?secret|"
    r"password|passwd|secret|token"
    r")\b"
)

_INLINE_SECRET_RE = re.compile(
    r"(?i)\b("
    r"api[_-]?key|authorization|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|secret|token"
    r")\s*([:=])\s*([^\s,;]+)"
)

_BEARER_RE = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+")


def state_dir() -> Path:
    return Path(os.environ.get("HERMES_PET_HOME") or "~/.hermes_pet").expanduser()


def jobs_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir).expanduser() if base_dir is not None else state_dir()
    return root / "jobs.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_job_id() -> str:
    return str(uuid4())


def redact_text(value: str, *, limit: int = OUTPUT_SUMMARY_LIMIT) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    text = _INLINE_SECRET_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", text)
    text = _BEARER_RE.sub(lambda match: f"{match.group(1)} [redacted]", text)
    if len(text) <= limit:
        return text
    return text[-limit:].lstrip()


def redact_command(command: list[str]) -> tuple[list[str], bool]:
    redacted: list[str] = []
    changed = False
    redact_next = False

    for raw_part in command:
        part = str(raw_part)
        lower = part.lower()
        if redact_next:
            redacted.append("[redacted]")
            changed = True
            redact_next = False
            continue

        if lower in _SENSITIVE_FLAG_NAMES:
            redacted.append(part)
            redact_next = True
            continue

        if lower.startswith(tuple(flag + "=" for flag in _SENSITIVE_FLAG_NAMES)):
            key = part.split("=", 1)[0]
            redacted.append(f"{key}=[redacted]")
            changed = True
            continue

        if _SENSITIVE_KEY_RE.search(part) and "=" in part:
            safe = _INLINE_SECRET_RE.sub(
                lambda match: f"{match.group(1)}{match.group(2)}[redacted]",
                part,
            )
            redacted.append(safe)
            changed = changed or safe != part
            continue

        redacted.append(part)

    return redacted, changed


def load_jobs(base_dir: str | Path | None = None) -> list[dict[str, Any]]:
    path = jobs_path(base_dir)
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


def save_jobs(jobs: list[dict[str, Any]], base_dir: str | Path | None = None) -> None:
    path = jobs_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    bounded = jobs[-HISTORY_LIMIT:]
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(bounded, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    tmp_path.replace(path)


def append_job(job: dict[str, Any], base_dir: str | Path | None = None) -> None:
    jobs = load_jobs(base_dir)
    jobs.append(job)
    save_jobs(jobs, base_dir)


def recent_jobs(
    *,
    base_dir: str | Path | None = None,
    failed_only: bool = False,
    status: str | None = None,
    query: str | None = None,
    limit: int | None = None,
    newest_first: bool = True,
) -> list[dict[str, Any]]:
    jobs = load_jobs(base_dir)
    if failed_only:
        jobs = [job for job in jobs if job.get("status") == "failed" or job.get("exit_code") not in (0, None)]
    if status:
        normalized = str(status).strip().lower()
        if normalized == "failed":
            jobs = [job for job in jobs if job.get("status") == "failed" or job.get("exit_code") not in (0, None)]
        elif normalized in {"succeeded", "success"}:
            jobs = [job for job in jobs if job.get("status") == "succeeded" or job.get("exit_code") == 0]
        elif normalized not in {"all", "*"}:
            jobs = [job for job in jobs if str(job.get("status") or "").lower() == normalized]
    if query:
        needle = str(query).strip().lower()
        if needle:
            jobs = [job for job in jobs if _job_search_text(job).find(needle) >= 0]
    if limit is not None:
        jobs = jobs[-max(0, limit):]
    if newest_first:
        jobs = list(reversed(jobs))
    return jobs


def latest_failed_job(base_dir: str | Path | None = None) -> dict[str, Any] | None:
    for job in reversed(load_jobs(base_dir)):
        if job.get("status") == "failed" or job.get("exit_code") not in (0, None):
            return job
    return None


def _job_search_text(job: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("id", "name", "status", "output_summary", "error_summary"):
        value = job.get(key)
        if value is not None:
            parts.append(str(value))
    command = job.get("command")
    if isinstance(command, list):
        parts.extend(str(part) for part in command)
    elif command is not None:
        parts.append(str(command))
    return " ".join(parts).lower()


def job_scan_summary(jobs: list[dict[str, Any]]) -> dict[str, int]:
    failed = [job for job in jobs if job.get("status") == "failed" or job.get("exit_code") not in (0, None)]
    succeeded = [job for job in jobs if job.get("status") == "succeeded" or job.get("exit_code") == 0]
    retryable_failures = [job for job in failed if job.get("retryable") is not False and not job.get("command_redacted")]
    return {
        "total": len(jobs),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "retryable_failures": len(retryable_failures),
    }


def compact_jobs(*, base_dir: str | Path | None = None, keep: int = HISTORY_LIMIT) -> dict[str, int]:
    jobs = load_jobs(base_dir)
    keep = max(0, min(int(keep), HISTORY_LIMIT))
    kept = jobs[-keep:] if keep else []
    save_jobs(kept, base_dir)
    return {"before": len(jobs), "after": len(kept), "removed": max(0, len(jobs) - len(kept))}
