from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pytest

from hermes_pet import cli
from hermes_pet.jobs import (
    append_job,
    jobs_path,
    latest_failed_job,
    recent_jobs,
    redact_command,
    redact_text,
    save_jobs,
)
from hermes_pet.prefs import normalize_prefs, save_prefs


def test_normalize_prefs_clamps_values_and_expires_mute() -> None:
    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)

    prefs = normalize_prefs(
        {
            "quiet_mode": "LOUD",
            "bubble_throttle_seconds": "99999",
            "muted_until": "2026-05-06T11:59:59Z",
            "show_tray_on_urgent": "",
            "show_idle_bubbles": 1,
            "unknown": "ignored",
        },
        now=now,
    )

    assert prefs == {
        "muted_until": None,
        "quiet_mode": "off",
        "bubble_throttle_seconds": 3600.0,
        "show_tray_on_urgent": False,
        "show_idle_bubbles": True,
    }


def test_save_prefs_writes_normalized_json(tmp_path) -> None:
    saved = save_prefs({"quiet_mode": "silent", "bubble_throttle_seconds": -5}, tmp_path)

    assert saved["quiet_mode"] == "silent"
    assert saved["bubble_throttle_seconds"] == 0.0
    assert json.loads((tmp_path / "notification-prefs.json").read_text(encoding="utf-8")) == saved


def test_redact_command_marks_sensitive_args_non_retryable() -> None:
    command, changed = redact_command(
        ["deploy", "--token", "abc123", "--client-secret=xyz", "password=hunter2", "safe"]
    )

    assert changed is True
    assert command == [
        "deploy",
        "--token",
        "[redacted]",
        "--client-secret=[redacted]",
        "password=[redacted]",
        "safe",
    ]


def test_job_history_bounds_and_filters_failures(tmp_path) -> None:
    save_jobs(
        [
            {"id": str(index), "status": "succeeded", "exit_code": 0}
            for index in range(105)
        ],
        tmp_path,
    )
    append_job({"id": "failed", "status": "failed", "exit_code": 7}, tmp_path)

    stored = json.loads(jobs_path(tmp_path).read_text(encoding="utf-8"))

    assert len(stored) == 100
    assert stored[0]["id"] == "6"
    assert latest_failed_job(tmp_path)["id"] == "failed"
    assert recent_jobs(base_dir=tmp_path, failed_only=True, newest_first=False) == [
        {"id": "failed", "status": "failed", "exit_code": 7}
    ]


def test_retry_refuses_redacted_failed_job(tmp_path, monkeypatch) -> None:
    save_jobs(
        [
            {
                "name": "deploy",
                "status": "failed",
                "exit_code": 1,
                "command": ["deploy", "--token", "[redacted]"],
                "command_redacted": True,
                "retryable": False,
            }
        ],
        tmp_path,
    )
    monkeypatch.setenv("HERMES_PET_HOME", str(tmp_path))
    monkeypatch.setattr(
        cli,
        "_run_wrapped_command",
        lambda *args, **kwargs: pytest.fail("redacted commands must not be retried"),
    )

    with pytest.raises(cli.PetCLIError, match="cannot be retried safely"):
        cli._cmd_retry(argparse.Namespace(status_interval=0))


def test_redact_text_handles_inline_and_bearer_secrets() -> None:
    redacted = redact_text("request failed bearer abc.def token=secret password=hunter2")

    assert "abc.def" not in redacted
    assert "secret" not in redacted
    assert "hunter2" not in redacted
    assert "bearer [redacted]" in redacted
