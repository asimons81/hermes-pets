from __future__ import annotations

import argparse
import json

import pytest

from hermes_pet import cli, event_log
from hermes_pet.custom_pets import (
    custom_pet_event_payload,
    import_package,
    list_custom_pets,
    set_current_custom_pet,
    validate_pet_name,
)
from hermes_pet.jobs import load_jobs, save_jobs
from hermes_pet.prefs import save_prefs


PNG_BYTES = b"\x89PNG\r\n\x1a\nminimal"


def _write_png(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_BYTES)


def _make_custom_pet(root, *, name: str = "source"):
    package = root / name
    _write_png(package / "sprites" / "idle" / "idle_00.png")
    _write_png(package / "sprites" / "running-right" / "0.png")
    (package / "custom-pet.json").write_text(
        json.dumps({"name": name, "states": {"idle": {"fps": 6}}}),
        encoding="utf-8",
    )
    return package


def test_event_log_redacts_text_and_drops_unsafe_keys(tmp_path) -> None:
    event_log.append_event(
        {
            "type": "message_received",
            "text": "deploy failed token=supersecret",
            "sender": "Ada api_key=abc123",
            "open_command": "curl --token supersecret",
            "unexpected": "secret",
            "urgent": "yes",
        },
        base_dir=tmp_path,
    )

    stored = json.loads(event_log.events_path(tmp_path).read_text(encoding="utf-8"))

    assert stored == [
        {
            "sender": "Ada api_key=[redacted]",
            "text": "deploy failed token=[redacted]",
            "type": "message_received",
            "urgent": True,
        }
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


def test_import_select_and_list_custom_pet(tmp_path) -> None:
    source = _make_custom_pet(tmp_path)
    dest = import_package(source, name="operator", base_dir=tmp_path)
    payload = set_current_custom_pet("operator", base_dir=tmp_path)
    pets = list_custom_pets(tmp_path)

    assert dest == tmp_path / "custom-pets" / "operator"
    assert payload["name"] == "operator"
    assert payload["manifest"]["states"]["idle"]["frames"] == ["idle_00.png"]
    assert custom_pet_event_payload(tmp_path)["name"] == "operator"
    assert pets == [
        {
            "name": "operator",
            "path": str(dest),
            "valid": True,
            "states": ["idle", "run_right"],
            "current": True,
        }
    ]


def test_validate_pet_name_rejects_paths_and_bad_prefixes() -> None:
    assert validate_pet_name("demo_pet-1") == "demo_pet-1"
    assert validate_pet_name("Upper") == "upper"

    for name in ("../escape", "", "-starts-bad"):
        with pytest.raises(ValueError):
            validate_pet_name(name)


def test_doctor_strict_fails_when_checks_warn(monkeypatch, tmp_path) -> None:
    class Bridge:
        _WEBSOCKETS_AVAILABLE = True

        @staticmethod
        def is_bridge_available(*, port, host):
            return False

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: Bridge)
    monkeypatch.setattr(cli, "_state_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "_overlay_dir", lambda: tmp_path / "overlay")
    monkeypatch.setattr(cli, "_is_wsl", lambda: False)
    monkeypatch.setattr(cli.shutil, "which", lambda command: "/tmp/hermes-pet" if command == "hermes-pet" else None)

    assert cli._cmd_doctor(argparse.Namespace(strict=False)) == 0
    assert cli._cmd_doctor(argparse.Namespace(strict=True)) == 1


def test_state_export_includes_redacted_local_activity(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_state_dir", lambda: tmp_path)
    save_prefs({"quiet_mode": "important"}, tmp_path)
    save_jobs(
        [
            {
                "id": "job-1",
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
    event_log.append_event(
        {"type": "message_received", "text": "token=secret", "sender": "Ada", "created_at": "2026-05-06T12:00:00Z"},
        base_dir=tmp_path,
    )

    payload = cli._build_state_export(argparse.Namespace(since="", limit=10, event_limit=10, no_pet=True))

    assert payload["schema"] == "hermes.pet.export.v1"
    assert payload["prefs"]["notification_profile"] == "focus"
    assert payload["jobs"][0]["command"] == ["deploy", "--token", "[redacted]"]
    assert payload["summary"]["jobs"]["failed"] == 1
    assert payload["events"][0]["text"] == "token=[redacted]"


def test_state_cleanup_dry_run_preserves_history(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(cli, "_state_dir", lambda: tmp_path)
    save_jobs([{"id": "old"}, {"id": "new"}], tmp_path)
    event_log.append_event({"type": "status", "text": "one"}, base_dir=tmp_path)

    assert cli._cmd_state_cleanup(argparse.Namespace(keep_jobs=1, keep_events=0, dry_run=True)) == 0

    assert "Would remove 1 job(s) and 1 event(s)" in capsys.readouterr().out
    assert len(load_jobs(tmp_path)) == 2
