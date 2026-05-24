from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta

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


def test_event_log_persists_clean_phase4_context_only(tmp_path) -> None:
    event_log.append_event(
        {
            "schema": "hermes.pet.event.v1",
            "type": "approval_needed",
            "text": "Review token=secret",
            "source": "github",
            "source_id": "issue-16",
            "urgency": "urgent",
            "project_id": "hermes-pet",
            "project_path": "/home/tony/projects/hermes-pet",
            "session_id": "session-1",
            "session_label": "Phase 4",
            "action_label": "Open issue",
            "action_command": "gh issue view 16 --token secret",
            "action_url": "https://github.com/asimons81/hermes-pets/issues/16",
            "privacy_summary": "Body redacted; token=secret",
            "metadata": {"token": "secret"},
        },
        base_dir=tmp_path,
    )

    stored = json.loads(event_log.events_path(tmp_path).read_text(encoding="utf-8"))[0]

    assert stored["schema"] == "hermes.pet.event.v1"
    assert stored["urgency"] == "urgent"
    assert stored["source"] == "github"
    assert stored["source_id"] == "issue-16"
    assert stored["project_id"] == "hermes-pet"
    assert stored["session_id"] == "session-1"
    assert stored["action_label"] == "Open issue"
    assert stored["action_command"] == "gh issue view 16 --token [redacted]"
    assert stored["privacy_summary"] == "Body redacted; token=[redacted]"
    assert "metadata" not in stored


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


def test_preview_installed_custom_pet_writes_html(tmp_path, monkeypatch, capsys) -> None:
    source = _make_custom_pet(tmp_path)
    import_package(source, name="operator", base_dir=tmp_path)
    output = tmp_path / "preview.html"
    monkeypatch.setattr(cli, "_state_dir", lambda: tmp_path)

    assert cli._cmd_custom_pet_preview(
        argparse.Namespace(path="", installed="operator", name=None, output=str(output), open=False, no_open=True)
    ) == 0

    assert output.is_file()
    assert "data:image/png;base64," in output.read_text(encoding="utf-8")
    text = capsys.readouterr().out
    assert "Custom pet preview: operator" in text
    assert "run_right" in text


def test_preview_rejects_invalid_custom_pet(tmp_path) -> None:
    bad_package = tmp_path / "bad"
    bad_package.mkdir()

    with pytest.raises(cli.PetCLIError, match="Custom pet preview failed"):
        cli._cmd_custom_pet_preview(
            argparse.Namespace(path=str(bad_package), installed="", name=None, output="", open=False, no_open=True)
        )


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


def test_launch_bridge_and_overlay_uses_replace_mode_with_windows_launcher(monkeypatch, tmp_path) -> None:
    overlay_dir = tmp_path / "overlay"
    launcher = overlay_dir / "scripts" / "launch-windows-overlay.ps1"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("# launcher placeholder\n", encoding="utf-8")

    class Bridge:
        PET_BRIDGE_DEFAULT_PORT = 17473

        @staticmethod
        def is_bridge_available(*, port, host):
            return True

    captured_cmd: list[str] = []
    captured_kwargs: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        nonlocal captured_cmd, captured_kwargs
        captured_cmd = list(cmd)
        captured_kwargs = kwargs
        return cli.subprocess.CompletedProcess(cmd, 0, stdout="overlay ok\n", stderr="")

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: Bridge)
    monkeypatch.setattr(cli, "_state_dir", lambda: tmp_path / "state")
    monkeypatch.setattr(cli, "_overlay_dir", lambda: overlay_dir)
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "_is_wsl", lambda: True)
    monkeypatch.setattr(cli.shutil, "which", lambda command: "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" if command == "powershell.exe" else None)
    monkeypatch.setattr(cli, "_wsl_to_windows_path", lambda path: f"WIN:{path.name}")
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert cli._launch_bridge_and_overlay(argparse.Namespace(replace=True)) == 0
    assert captured_cmd[0] == "powershell.exe"
    assert "-Replace" in captured_cmd
    assert captured_kwargs["cwd"] == str(tmp_path)


def test_close_only_stops_bridge_processes_when_requested(monkeypatch, tmp_path) -> None:
    class Bridge:
        PET_BRIDGE_DEFAULT_PORT = 17473

    launcher_calls: list[tuple[int, str]] = []
    bridge_stop_calls: list[int] = []

    def fake_run_overlay_launcher(*, port, mode):
        launcher_calls.append((port, mode))
        return cli.subprocess.CompletedProcess(["powershell.exe"], 0, stdout="Overlay processes: none\n", stderr="")

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: Bridge)
    monkeypatch.setattr(cli, "_run_overlay_launcher", fake_run_overlay_launcher)
    monkeypatch.setattr(cli, "_stop_bridge_processes", lambda port: bridge_stop_calls.append(port) or 2)

    assert cli._cmd_close(argparse.Namespace(bridge=False)) == 0
    assert launcher_calls == [(17473, "stop")]
    assert bridge_stop_calls == []

    assert cli._cmd_close(argparse.Namespace(bridge=True)) == 0
    assert launcher_calls == [(17473, "stop"), (17473, "stop")]
    assert bridge_stop_calls == [17473]


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


def test_state_export_cleans_raw_phase4_event_metadata(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_state_dir", lambda: tmp_path)
    event_log.events_path(tmp_path).write_text(
        json.dumps(
            [
                {
                    "schema": "hermes.pet.event.v1",
                    "type": "approval_needed",
                    "text": "Review token=secret",
                    "source": "github token=secret",
                    "source_id": "issue-18",
                    "project_path": "/tmp/token=secret/repo",
                    "session_label": "Phase token=secret",
                    "action_label": "Open token=secret",
                    "action_command": "deploy --token secret",
                    "action_url": "https://example.test/hook?token=secret",
                    "privacy_summary": "Local path token=secret was removed.",
                    "raw_metadata": {"token": "secret"},
                }
            ]
        ),
        encoding="utf-8",
    )

    payload = cli._build_state_export(argparse.Namespace(since="", limit=10, event_limit=10, no_pet=True))
    event = payload["events"][0]

    assert event["text"] == "Review token=[redacted]"
    assert event["source"] == "github token=[redacted]"
    assert event["project_path"].startswith("/tmp/token=[redacted]")
    assert event["session_label"] == "Phase token=[redacted]"
    assert event["action_label"] == "Open token=[redacted]"
    assert event["action_command"] == "deploy --token [redacted]"
    assert event["action_url"] == "https://example.test/hook?token=[redacted]"
    assert event["privacy_summary"] == "Local path token=[redacted] was removed."
    assert "raw_metadata" not in event
    assert "secret" not in json.dumps(event)


def test_raw_event_file_drops_unsafe_action_url(tmp_path) -> None:
    event_log.events_path(tmp_path).write_text(
        json.dumps(
            [
                {
                    "schema": "hermes.pet.event.v1",
                    "type": "approval_needed",
                    "text": "Review",
                    "action_url": "javascript:alert(1)",
                },
                {
                    "schema": "hermes.pet.event.v1",
                    "type": "approval_needed",
                    "text": "Review safe URL",
                    "action_url": "https://example.test/review?token=secret",
                },
            ]
        ),
        encoding="utf-8",
    )

    events = event_log.load_events(tmp_path)

    assert "action_url" not in events[0]
    assert events[1]["action_url"] == "https://example.test/review?token=[redacted]"


def test_event_context_prefers_cli_over_env(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_PET_PROJECT_ID", "env-project")
    monkeypatch.setenv("HERMES_PET_PROJECT_PATH", "/env/project")
    monkeypatch.setenv("HERMES_PET_SESSION_ID", "env-session")
    monkeypatch.setenv("HERMES_PET_SESSION_LABEL", "Env Session")

    context = cli._event_context_from_args(
        argparse.Namespace(
            project_id="cli-project",
            project_path="",
            session_id="",
            session_label="CLI Session",
        )
    )

    assert context == {
        "project_id": "cli-project",
        "project_path": "/env/project",
        "session_id": "env-session",
        "session_label": "CLI Session",
    }


def test_event_context_flags_are_shared_across_emitters() -> None:
    parser = cli._build_parser()
    commands = [
        ["emit", "status", "hello", "--project-id", "hermes-pet"],
        ["message", "--source", "telegram", "--sender", "Ada", "--project-id", "hermes-pet", "hello"],
        ["brief", "--emit", "--project-id", "hermes-pet"],
        ["run", "--project-id", "hermes-pet", "--", sys.executable, "-c", "pass"],
        ["wrap", "--name", "smoke", "--project-id", "hermes-pet", "--", sys.executable, "-c", "pass"],
    ]

    for argv in commands:
        args = parser.parse_args(argv)
        assert args.project_id == "hermes-pet"


def test_event_context_infers_git_project_for_wrapped_commands(monkeypatch, tmp_path) -> None:
    for key in (
        "HERMES_PET_PROJECT_ID",
        "HERMES_PET_PROJECT_PATH",
        "HERMES_PET_SESSION_ID",
        "HERMES_PET_SESSION_LABEL",
    ):
        monkeypatch.delenv(key, raising=False)

    repo = tmp_path / "demo-repo"
    repo.mkdir()

    class Result:
        returncode = 0
        stdout = f"{repo}\n"

    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: Result())

    context = cli._event_context_from_args(
        argparse.Namespace(project_id="", project_path="", session_id="", session_label=""),
        infer_project=True,
    )

    assert context == {
        "project_id": "demo-repo",
        "project_path": str(repo),
    }


def test_message_context_and_open_command_reach_event(monkeypatch) -> None:
    captured = {}

    def fake_send(event_type, text, *, required, **extra):
        captured.update({"event_type": event_type, "text": text, "required": required, "extra": extra})
        return True, {"type": event_type, "text": text, "source": extra["source"], "sender": extra["sender"]}

    monkeypatch.setattr(cli, "_send_pet_event", fake_send)

    assert cli._cmd_message(
        argparse.Namespace(
            source="telegram",
            sender="Ada",
            text=["Can", "you", "review?"],
            urgent=False,
            open_command="gh issue view 19",
            project_id="hermes-pet",
            project_path="",
            session_id="session-1",
            session_label="",
        )
    ) == 0

    assert captured["event_type"] == "message_received"
    assert captured["extra"]["action_command"] == "gh issue view 19"
    assert captured["extra"]["project_id"] == "hermes-pet"
    assert captured["extra"]["session_id"] == "session-1"


def test_send_pet_event_broadcasts_privacy_safe_payload(monkeypatch, tmp_path) -> None:
    sent = {}

    class Bridge:
        @staticmethod
        def send_event_to_bridge(event, *, port, host, bridge_url):
            sent.update(event)
            return True

    monkeypatch.setattr(cli, "_state_dir", lambda: tmp_path)
    monkeypatch.setattr(cli.importlib, "import_module", lambda name: Bridge)

    ok, event = cli._send_pet_event(
        "message_received",
        "Review token=secret",
        required=True,
        source="telegram",
        sender="Ada",
        action_command="deploy --token secret",
        action_url="https://example.test/review?token=secret",
        privacy_summary="Contains token=secret",
    )

    stored = json.loads(event_log.events_path(tmp_path).read_text(encoding="utf-8"))[0]

    assert ok is True
    assert event == sent == stored
    assert sent["text"] == "Review token=[redacted]"
    assert sent["action_command"] == "deploy --token [redacted]"
    assert sent["action_url"] == "https://example.test/review?token=[redacted]"
    assert sent["privacy_summary"] == "Contains token=[redacted]"
    assert "secret" not in json.dumps(sent)


def test_wrapped_command_events_include_context(monkeypatch) -> None:
    emitted = []

    def fake_send(event_type, text, *, required, **extra):
        emitted.append({"type": event_type, "text": text, "extra": extra})
        return True, {"type": event_type, "text": text, **extra}

    monkeypatch.setattr(cli, "_send_pet_event", fake_send)
    monkeypatch.setattr(cli, "_record_job", lambda **kwargs: None)

    result = cli._run_wrapped_command_with_context(
        [sys.executable, "-c", "pass"],
        name="context smoke",
        status_interval=0,
        event_context={"project_id": "hermes-pet", "session_id": "session-1"},
    )

    assert result == 0
    assert [event["type"] for event in emitted] == ["job_started", "job_finished"]
    assert all(event["extra"]["project_id"] == "hermes-pet" for event in emitted)
    assert all(event["extra"]["session_id"] == "session-1" for event in emitted)


def test_brief_prioritizes_urgent_grouped_actionable_events(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_state_dir", lambda: tmp_path)
    event_log.append_event(
        cli.build_event(
            "message_received",
            "Can you review?",
            source="telegram",
            sender="Ada",
            project_id="hermes-pet",
            session_label="Phase 4",
            action_command="gh issue view 17",
        ),
        base_dir=tmp_path,
    )
    event_log.append_event(
        cli.build_event(
            "approval_needed",
            "Deploy plan needs review",
            urgency="urgent",
            project_id="hermes-pet",
            session_label="Phase 4",
            action_label="Review plan",
            action_url="https://example.test/plan",
        ),
        base_dir=tmp_path,
    )

    brief = cli._build_brief(since=timedelta(days=1))
    telegram = cli._build_brief(since=timedelta(days=1), telegram_text=True)

    assert "By project/session:" in brief
    assert "hermes-pet / Phase 4: 2 event(s)" in brief
    assert "Top local events:" in brief
    assert "Hint: Review plan" in brief
    assert "Suggested next action: Handle urgent local event" in brief
    top_line = next(line for line in brief.splitlines() if line.startswith("Top local events:"))
    assert top_line.index("Deploy plan needs review") < top_line.index("telegram from Ada")
    assert "Urgent: 1" in telegram
    assert "Group: hermes-pet / Phase 4" in telegram
    assert "gh issue view 17" in telegram


def test_state_cleanup_dry_run_preserves_history(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(cli, "_state_dir", lambda: tmp_path)
    save_jobs([{"id": "old"}, {"id": "new"}], tmp_path)
    event_log.append_event({"type": "status", "text": "one"}, base_dir=tmp_path)

    assert cli._cmd_state_cleanup(argparse.Namespace(keep_jobs=1, keep_events=0, dry_run=True)) == 0

    assert "Would remove 1 job(s) and 1 event(s)" in capsys.readouterr().out
    assert len(load_jobs(tmp_path)) == 2
