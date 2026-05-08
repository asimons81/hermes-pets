from __future__ import annotations

import argparse
import json
import shlex
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from hermes_pet import cli
from hermes_pet.achievements import (
    ACHIEVEMENT_DEFINITIONS,
    achievement_status,
    achievements_path,
    load_achievement_state,
    save_achievement_state,
    sync_achievements,
    unlock_achievement,
)
from hermes_pet.custom_pets import clear_current_custom_pet, import_package, set_current_custom_pet
from hermes_pet.dashboard import (
    DashboardError,
    DashboardHTTPServer,
    adopt_dashboard_species,
    build_state_snapshot,
    clear_dashboard_custom_pet,
    emit_dashboard_test_event,
    get_dashboard_voice,
    hatch_dashboard_random_pet,
    import_dashboard_custom_pet,
    list_dashboard_species_catalog,
    require_dashboard_assets,
    test_dashboard_voice as run_dashboard_voice_test,
    update_dashboard_voice,
    update_dashboard_prefs,
)
from hermes_pet.engine import Pet, load_pet, save_pet
from hermes_pet.jobs import save_jobs
from hermes_pet.prefs import load_prefs, save_prefs
from hermes_pet.voice import (
    load_voice_prefs,
    run_voice_for_event,
    run_voice_test,
    save_voice_prefs,
    voice_status,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\nminimal"


def _python_command(script: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_BYTES)


def _make_custom_pet(root: Path, *, name: str = "source") -> Path:
    package = root / name
    _write_png(package / "sprites" / "idle" / "idle_00.png")
    (package / "custom-pet.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    return package


def test_dashboard_assets_and_parser_are_available() -> None:
    assert require_dashboard_assets().joinpath("index.html").is_file()
    args = cli._build_parser().parse_args(["dashboard", "--no-open"])
    assert args.host == "127.0.0.1"
    assert args.port == 17474
    assert args.no_open is True
    assert cli._build_parser().parse_args(["dashboard", "--port", "0", "--no-open"]).port == 0


def test_dashboard_voice_ui_sanitizes_results_and_env_command() -> None:
    root = require_dashboard_assets()
    app_js = root.joinpath("app.js").read_text(encoding="utf-8")
    index_html = root.joinpath("index.html").read_text(encoding="utf-8")

    assert "JSON.stringify(result.result" not in app_js
    assert "result.stdout" not in app_js
    assert "result.stderr" not in app_js
    assert "command_source === 'env'" in app_js
    assert "body.command =" in app_js
    assert 'role="status"' in index_html
    assert 'aria-atomic="true"' in index_html
    assert 'aria-controls="voiceResult"' in index_html


def test_dashboard_http_requires_token(tmp_path) -> None:
    server = DashboardHTTPServer(("127.0.0.1", 0), "secret-token", tmp_path, quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/state"
    try:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(url, timeout=2)
        assert excinfo.value.code == 401

        req = urllib.request.Request(url, headers={"X-Hermes-Pet-Token": "secret-token"})
        with urllib.request.urlopen(req, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["schema"] == "hermes.pet.dashboard.v1"
        assert payload["server"]["localhost_only"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_state_handles_empty_and_populated_temp_home(tmp_path) -> None:
    empty = build_state_snapshot(base_dir=tmp_path)
    assert empty["pet"] is None
    assert empty["custom_pets"] == []
    assert empty["achievements"]["total_count"] >= 1

    pet = Pet.hatch("", force_seed=1)
    pet.xp = 260
    pet.level = 6
    save_pet(pet, state_dir=tmp_path)
    source = _make_custom_pet(tmp_path)
    import_package(source, name="operator", base_dir=tmp_path)
    set_current_custom_pet("operator", base_dir=tmp_path)
    save_jobs(
        [
            {"name": "tests", "status": "succeeded", "exit_code": 0},
            {"name": "deploy", "status": "failed", "exit_code": 1, "retryable": True},
        ],
        tmp_path,
    )

    populated = build_state_snapshot(base_dir=tmp_path)
    assert populated["pet"]["level"] == 6
    assert populated["custom_pet"]["name"] == "operator"
    assert populated["job_summary"]["failed"] == 1
    unlocked = {item["id"] for item in populated["achievements"]["items"] if item["unlocked"]}
    assert {"first_custom_pet_imported", "first_custom_pet_selected", "first_wrapped_job_completed", "level_5"} <= unlocked


def test_dashboard_custom_pet_import_rejects_duplicates_and_unlocks(tmp_path) -> None:
    source = _make_custom_pet(tmp_path)
    result = import_dashboard_custom_pet({"path": str(source), "name": "operator"}, tmp_path)
    assert result["imported"]["name"] == "operator"
    assert "first_custom_pet_imported" in load_achievement_state(tmp_path)["unlocked"]
    with pytest.raises(Exception, match="already exists"):
        import_dashboard_custom_pet({"path": str(source), "name": "operator"}, tmp_path)


def test_dashboard_species_catalog_and_no_pet_adoption(tmp_path) -> None:
    catalog = list_dashboard_species_catalog(tmp_path)
    names = {item["name"] for item in catalog["species"]}
    assert "cat" in names
    assert catalog["current"] is None

    result = adopt_dashboard_species({"species": "cat"}, tmp_path)
    assert result["action"] == "adopt_species"
    assert result["pet"]["species"] == "cat"
    assert result["pet"]["level"] == 1
    assert result["pet"]["xp"] == 0
    assert result["custom_pet"] is None
    assert result["snapshot"]["pet"]["species"] == "cat"


def test_dashboard_species_adoption_replaces_existing_pet_and_clears_custom_selection(tmp_path) -> None:
    pet = Pet.hatch("", force_seed=1)
    pet.species = "duck"
    pet.level = 8
    pet.xp = 777
    pet.total_interactions = 12
    pet.milestones = ["level_5"]
    save_pet(pet, state_dir=tmp_path)
    source = _make_custom_pet(tmp_path)
    import_package(source, name="operator", base_dir=tmp_path)
    set_current_custom_pet("operator", base_dir=tmp_path)

    result = adopt_dashboard_species({"species": "dragon"}, tmp_path)
    saved = load_pet("", state_dir=tmp_path)
    assert saved is not None
    assert saved.species == "dragon"
    assert saved.level == 1
    assert saved.xp == 0
    assert saved.total_interactions == 0
    assert saved.milestones == []
    assert result["custom_selection_cleared"] is True
    assert result["snapshot"]["custom_pet"] is None
    assert (tmp_path / "custom-pets" / "operator").is_dir()


def test_dashboard_species_adoption_rejects_invalid_species_and_bad_json_shape(tmp_path) -> None:
    with pytest.raises(DashboardError, match="Unknown species"):
        adopt_dashboard_species({"species": "not-real"}, tmp_path)
    with pytest.raises(DashboardError, match="Expected a JSON object"):
        adopt_dashboard_species([], tmp_path)  # type: ignore[arg-type]


def test_dashboard_random_hatch_creates_pet_and_clears_custom_selection(tmp_path) -> None:
    source = _make_custom_pet(tmp_path)
    import_package(source, name="operator", base_dir=tmp_path)
    set_current_custom_pet("operator", base_dir=tmp_path)

    result = hatch_dashboard_random_pet(tmp_path)
    saved = load_pet("", state_dir=tmp_path)
    assert saved is not None
    assert result["action"] == "random_hatch"
    assert result["pet"]["species"] == saved.species
    assert result["pet"]["level"] == 1
    assert result["custom_selection_cleared"] is True
    assert result["snapshot"]["custom_pet"] is None


def test_dashboard_clear_custom_selection_keeps_installed_package(tmp_path) -> None:
    source = _make_custom_pet(tmp_path)
    import_package(source, name="operator", base_dir=tmp_path)
    set_current_custom_pet("operator", base_dir=tmp_path)

    result = clear_dashboard_custom_pet(tmp_path)
    assert result["cleared"] is True
    assert result["current"] is None
    assert result["custom_pet"] is None
    assert (tmp_path / "custom-pets" / "operator").is_dir()
    assert not (tmp_path / "custom-pet-current.json").exists()


def test_custom_pet_clear_helper_is_non_destructive_and_idempotent(tmp_path) -> None:
    source = _make_custom_pet(tmp_path)
    import_package(source, name="current", base_dir=tmp_path)
    set_current_custom_pet("current", base_dir=tmp_path)

    assert clear_current_custom_pet(tmp_path) is True
    assert clear_current_custom_pet(tmp_path) is False
    assert (tmp_path / "custom-pets" / "current").is_dir()


def test_dashboard_new_species_endpoint_requires_token(tmp_path) -> None:
    server = DashboardHTTPServer(("127.0.0.1", 0), "secret-token", tmp_path, quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/species"
    try:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(url, timeout=2)
        assert excinfo.value.code == 401

        req = urllib.request.Request(url, headers={"X-Hermes-Pet-Token": "secret-token"})
        with urllib.request.urlopen(req, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert any(item["name"] == "cat" for item in payload["species"])
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_adopt_endpoint_reports_invalid_json(tmp_path) -> None:
    server = DashboardHTTPServer(("127.0.0.1", 0), "secret-token", tmp_path, quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/pets/adopt"
    try:
        req = urllib.request.Request(
            url,
            data=b"{not json",
            headers={"Content-Type": "application/json", "X-Hermes-Pet-Token": "secret-token"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(req, timeout=2)
        assert excinfo.value.code == 400
        payload = json.loads(excinfo.value.read().decode("utf-8"))
        assert "Invalid JSON" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_prefs_reuse_normalization_and_notify_offline(tmp_path) -> None:
    result = update_dashboard_prefs(
        {
            "notification_profile": "focus",
            "bubble_throttle_seconds": 99999,
            "show_tray_on_urgent": False,
            "show_idle_bubbles": False,
        },
        tmp_path,
    )
    assert result["prefs"]["notification_profile"] == "focus"
    assert result["prefs"]["bubble_throttle_seconds"] == 3600.0
    assert load_prefs(tmp_path)["quiet_mode"] == "important"


def test_voice_preview_defaults_override_and_explicit_test(tmp_path, monkeypatch) -> None:
    assert load_voice_prefs(tmp_path)["enabled"] is False
    out = tmp_path / "voice.txt"
    command = _python_command(f"import sys, pathlib; pathlib.Path(r'{out}').write_text(sys.stdin.read())")
    save_voice_prefs({"enabled": True, "command": command}, tmp_path)

    result = run_voice_for_event({"type": "message_received", "text": "hello"}, base_dir=tmp_path)
    assert result["ok"] is True
    assert "stdout" not in result
    assert "stderr" not in result
    assert out.read_text(encoding="utf-8") == "hello"

    monkeypatch.setenv("HERMES_PET_TTS_COMMAND", command)
    status = voice_status(tmp_path)
    assert status["command_source"] == "env"
    assert run_voice_test("preview", tmp_path)["ok"] is True
    assert out.read_text(encoding="utf-8") == "preview"


def test_voice_respects_disabled_allowlist_and_silent_prefs(tmp_path) -> None:
    save_voice_prefs({"enabled": False, "command": "missing"}, tmp_path)
    assert run_voice_for_event({"type": "message_received", "text": "hello"}, base_dir=tmp_path)["reason"] == "voice-disabled"
    assert run_voice_for_event({"type": "status", "text": "hello"}, base_dir=tmp_path)["reason"] == "event-not-allowlisted"

    save_voice_prefs({"enabled": True, "command": "missing"}, tmp_path)
    save_prefs({"notification_profile": "silent"}, tmp_path)
    assert (
        run_voice_for_event({"type": "message_received", "text": "hello"}, base_dir=tmp_path)["reason"]
        == "quiet-mode-silent"
    )


def test_voice_failure_timeout_and_missing_command_are_sanitized(tmp_path) -> None:
    save_voice_prefs({"enabled": True, "command": ""}, tmp_path)
    missing = run_voice_for_event({"type": "message_received", "text": "hello"}, base_dir=tmp_path)
    assert missing == {"ok": False, "skipped": True, "reason": "voice-command-missing"}

    save_voice_prefs({"enabled": True, "command": "/tmp/hermes-pet-secret-token-command"}, tmp_path)
    not_found = run_voice_for_event({"type": "message_received", "text": "hello"}, base_dir=tmp_path)
    assert not_found["reason"] == "command-not-found"
    assert "/tmp/hermes-pet-secret-token-command" not in json.dumps(not_found)

    fail_command = _python_command("import sys; print('token=secret'); print('path=/tmp/secret', file=sys.stderr); sys.exit(7)")
    save_voice_prefs({"enabled": True, "command": fail_command}, tmp_path)
    failed = run_voice_for_event({"type": "message_received", "text": "hello"}, base_dir=tmp_path)
    assert failed["ok"] is False
    assert failed["exit_code"] == 7
    assert failed["reason"] == "command-failed"
    assert failed["output_redacted"] is True
    assert "secret" not in json.dumps(failed)
    assert "stdout" not in failed
    assert "stderr" not in failed

    slow_command = _python_command("import time; time.sleep(1)")
    save_voice_prefs({"enabled": True, "command": slow_command, "timeout_seconds": 0.25}, tmp_path)
    timed_out = run_voice_for_event({"type": "message_received", "text": "hello"}, base_dir=tmp_path)
    assert timed_out["reason"] == "timeout"


def test_dashboard_voice_normalizes_persists_and_sanitizes_results(tmp_path) -> None:
    saved = update_dashboard_voice({"enabled": True, "command": " missing ", "timeout_seconds": 99}, tmp_path)
    assert saved["prefs"]["enabled"] is True
    assert saved["prefs"]["command"] == "missing"
    assert saved["prefs"]["timeout_seconds"] == 30.0
    assert get_dashboard_voice(tmp_path)["prefs"]["command"] == "missing"

    with pytest.raises(DashboardError, match="Expected a JSON object"):
        update_dashboard_voice([], tmp_path)  # type: ignore[arg-type]
    with pytest.raises(DashboardError, match="Expected a JSON object"):
        run_dashboard_voice_test([], tmp_path)  # type: ignore[arg-type]

    fail_command = _python_command("import sys; print('token=secret'); sys.exit(2)")
    save_voice_prefs({"enabled": True, "command": fail_command}, tmp_path)
    result = run_dashboard_voice_test({"text": "dashboard text"}, tmp_path)["result"]
    assert result["reason"] == "command-failed"
    assert "secret" not in json.dumps(result)


def test_voice_bridge_unavailable_does_not_leak_adapter_details(tmp_path, monkeypatch, capsys) -> None:
    class Bridge:
        @staticmethod
        def send_event_to_bridge(event, *, port, host, bridge_url):
            return False

    fail_command = _python_command("import sys; print('token=secret', file=sys.stderr); sys.exit(3)")
    save_voice_prefs({"enabled": True, "command": fail_command}, tmp_path)
    monkeypatch.setattr(cli, "_state_dir", lambda: tmp_path)
    monkeypatch.setattr(cli.importlib, "import_module", lambda name: Bridge)

    ok, event = cli._send_pet_event("message_received", "hello", required=False, source="message")

    captured = capsys.readouterr()
    assert ok is False
    assert event["text"] == "hello"
    assert "Voice preview failed: command-failed" in captured.err
    assert "secret" not in captured.err


def test_achievement_unlocks_are_idempotent(tmp_path) -> None:
    first = unlock_achievement("first_failed_job_recorded", base_dir=tmp_path, source="test")
    second = unlock_achievement("first_failed_job_recorded", base_dir=tmp_path, source="test")
    assert first is not None
    assert second is None
    status = achievement_status(tmp_path)
    assert status["unlocked_count"] == 1


def test_achievement_metadata_and_old_state_compatibility(tmp_path) -> None:
    achievements_path(tmp_path).write_text(
        json.dumps(
            {
                "unlocked": {
                    "first_wrapped_job_completed": {
                        "unlocked_at": "2026-05-08T12:00:00Z",
                        "source": "old-state",
                        "icon": "persisted-visual-data",
                    },
                    "future_remote_badge": {"unlocked_at": "2026-05-08T12:01:00Z"},
                }
            }
        ),
        encoding="utf-8",
    )

    state = load_achievement_state(tmp_path)
    assert list(state["unlocked"]) == ["first_wrapped_job_completed"]
    assert state["unlocked"]["first_wrapped_job_completed"] == {
        "unlocked_at": "2026-05-08T12:00:00Z",
        "source": "old-state",
    }

    saved = save_achievement_state(
        {
            "unlocked": {
                "first_wrapped_job_completed": {
                    "unlocked_at": "2026-05-08T12:00:00Z",
                    "source": "old-state",
                    "tier": "should-not-persist",
                }
            }
        },
        tmp_path,
    )
    assert saved == state
    persisted = json.loads(achievements_path(tmp_path).read_text(encoding="utf-8"))
    assert persisted["unlocked"]["first_wrapped_job_completed"] == state["unlocked"]["first_wrapped_job_completed"]

    status = achievement_status(tmp_path)
    clean_run = next(item for item in status["items"] if item["id"] == "first_wrapped_job_completed")
    assert clean_run["unlocked"] is True
    assert clean_run["category"] == "Jobs"
    assert clean_run["icon"] == "OK"
    assert clean_run["tier"] == "Bronze"
    assert clean_run["accent"] == "success"
    assert clean_run["locked_hint"]
    assert isinstance(clean_run["sort_order"], int)
    assert all({"category", "icon", "tier", "accent", "locked_hint", "sort_order"} <= set(item) for item in status["items"])
    assert len(status["items"]) == len(ACHIEVEMENT_DEFINITIONS)


def test_expanded_scan_based_achievements_unlock_from_local_state(tmp_path) -> None:
    pet = Pet.hatch("", force_seed=1)
    pet.level = 25
    pet.xp = 1250
    save_pet(pet, state_dir=tmp_path)

    jobs = [{"name": "fail-first", "status": "failed", "exit_code": 1, "retryable": True}]
    jobs.extend({"name": f"success-{index}", "status": "succeeded", "exit_code": 0} for index in range(10))
    save_jobs(jobs, tmp_path)

    for index in range(3):
        import_package(_make_custom_pet(tmp_path, name=f"source-{index}"), name=f"operator-{index}", base_dir=tmp_path)

    save_prefs({"quiet_mode": "important"}, tmp_path)
    save_voice_prefs({"enabled": True, "command": ""}, tmp_path)

    sync_achievements(tmp_path)
    unlocked = {item["id"] for item in achievement_status(tmp_path)["items"] if item["unlocked"]}
    assert {
        "three_jobs_completed",
        "ten_jobs_completed",
        "failure_then_success",
        "custom_pet_collection_3",
        "level_15",
        "level_25",
        "prefs_saved",
        "quiet_mode_enabled",
        "voice_preview_enabled",
    } <= unlocked


def test_dashboard_action_achievements_are_idempotent(tmp_path) -> None:
    source = _make_custom_pet(tmp_path)
    import_package(source, name="operator", base_dir=tmp_path)
    set_current_custom_pet("operator", base_dir=tmp_path)

    emit_dashboard_test_event(tmp_path)
    update_dashboard_prefs({"quiet_mode": "silent"}, tmp_path)
    update_dashboard_voice({"enabled": True}, tmp_path)
    run_dashboard_voice_test({"text": "hello"}, tmp_path)
    clear_dashboard_custom_pet(tmp_path)
    adopt_dashboard_species({"species": "cat"}, tmp_path)

    first_state = load_achievement_state(tmp_path)["unlocked"]
    for achievement_id in {
        "first_test_event_sent",
        "prefs_saved",
        "quiet_mode_enabled",
        "voice_preview_enabled",
        "voice_test_ran",
        "first_builtin_pet_change",
        "custom_pet_cleared",
    }:
        assert achievement_id in first_state

    update_dashboard_prefs({"quiet_mode": "silent"}, tmp_path)
    run_dashboard_voice_test({"text": "hello again"}, tmp_path)
    second_state = load_achievement_state(tmp_path)["unlocked"]
    assert second_state["prefs_saved"]["unlocked_at"] == first_state["prefs_saved"]["unlocked_at"]
    assert second_state["voice_test_ran"]["unlocked_at"] == first_state["voice_test_ran"]["unlocked_at"]


def test_dashboard_state_endpoint_unlocks_dashboard_open(tmp_path) -> None:
    server = DashboardHTTPServer(("127.0.0.1", 0), "secret-token", tmp_path, quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/state"
    try:
        req = urllib.request.Request(url, headers={"X-Hermes-Pet-Token": "secret-token"})
        with urllib.request.urlopen(req, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        unlocked = {item["id"] for item in payload["achievements"]["items"] if item["unlocked"]}
        assert "first_dashboard_opened" in unlocked
    finally:
        server.shutdown()
        server.server_close()


def test_voice_cli_commands_use_temp_home(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HERMES_PET_HOME", str(tmp_path))
    assert cli._cmd_voice(argparse.Namespace(voice_action="on")) == 0
    assert load_voice_prefs(tmp_path)["enabled"] is True
    assert "Voice preview enabled" in capsys.readouterr().out
