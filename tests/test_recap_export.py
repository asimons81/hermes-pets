from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from hermes_pet import cli, recap_export
from hermes_pet.engine import Pet, save_pet
from hermes_pet.event_log import append_event
from hermes_pet.jobs import save_jobs


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fake_renderer(payload: dict[str, object], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 630), "white").save(output_path)
    return output_path


def test_build_recap_payload_prefers_approval_needed_and_redacts_paths(tmp_path: Path) -> None:
    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    save_pet(Pet(name="Hermes", species="cat", variant="normal", hat="none", level=4, xp=180), tmp_path)
    save_jobs(
        [
            {
                "id": "job-success",
                "name": "wrap recap",
                "status": "succeeded",
                "exit_code": 0,
                "created_at": _iso(now.replace(hour=9)),
                "finished_at": _iso(now.replace(hour=9, minute=1)),
                "output_summary": "wrote /home/tony/private/output token=secret",
            },
            {
                "id": "job-fail",
                "name": "publish",
                "status": "failed",
                "exit_code": 1,
                "created_at": _iso(now.replace(hour=10)),
                "finished_at": _iso(now.replace(hour=10, minute=1)),
                "error_summary": "failed in /home/tony/private token=secret",
            },
        ],
        tmp_path,
    )
    append_event(
        {
            "type": "approval_needed",
            "text": "Review /home/tony/private token=secret",
            "sender": "Ada",
            "created_at": _iso(now.replace(hour=11)),
        },
        base_dir=tmp_path,
    )

    payload = recap_export.build_recap_payload(since="24h", state_dir=tmp_path, now=now)
    encoded = json.dumps(payload, ensure_ascii=False)

    assert payload["dominant_moment"]["type"] == "approval_needed"
    assert payload["pet"]["name_or_label"] == "Hermes"
    assert payload["generated_at"] == "2026-05-06T12:00:00Z"
    assert payload["caption"].endswith("Local recap, not posted by Hermes Pets.")
    assert "/home/" not in encoded
    assert "token=secret" not in encoded
    assert payload["proof_points"]
    assert len(payload["proof_points"]) <= 2


def test_write_recap_bundle_writes_three_files_and_metadata(tmp_path: Path) -> None:
    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    save_pet(Pet(name="Hermes", species="cat", variant="normal", hat="none", level=4, xp=180), tmp_path)
    save_jobs(
        [
            {
                "id": "job-success",
                "name": "wrap recap",
                "status": "succeeded",
                "exit_code": 0,
                "created_at": _iso(now.replace(hour=9)),
                "finished_at": _iso(now.replace(hour=9, minute=1)),
                "output_summary": "bundle ready",
            }
        ],
        tmp_path,
    )
    append_event(
        {
            "type": "message_received",
            "text": "hello /home/tony/private token=secret",
            "sender": "Ada",
            "source": "telegram",
            "created_at": _iso(now.replace(hour=10)),
        },
        base_dir=tmp_path,
    )

    bundle_dir = recap_export.write_recap_bundle(
        since="24h",
        output_dir=tmp_path / "bundle",
        state_dir=tmp_path,
        now=now,
        renderer=_fake_renderer,
    )

    caption = (bundle_dir / "caption.txt").read_text(encoding="utf-8")
    metadata = json.loads((bundle_dir / "metadata.json").read_text(encoding="utf-8"))
    image = Image.open(bundle_dir / "recap-card.png")

    assert bundle_dir == (tmp_path / "bundle").resolve()
    assert image.size == (1200, 630)
    assert metadata["schema"] == "hermes.pet.recap_bundle.v1"
    assert metadata["bundle_files"]["recap-card.png"]["format"] == "PNG"
    assert metadata["pet"]["name_or_label"] == "Hermes"
    assert metadata["dominant_moment"]["type"] == "job_succeeded"
    assert caption == metadata["caption"] + "\n"
    assert "/home/" not in caption
    assert "token=secret" not in caption
    assert "/home/" not in json.dumps(metadata, ensure_ascii=False)
    assert "token=secret" not in json.dumps(metadata, ensure_ascii=False)


def test_resolve_output_dir_defaults_under_state_dir(tmp_path: Path) -> None:
    now = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)

    bundle_dir = recap_export.resolve_output_dir(None, state_dir=tmp_path, now=now)

    assert bundle_dir == (tmp_path / "exports" / "recaps" / "20260506T120000Z").resolve()


def test_cli_recap_export_prints_bundle_path(tmp_path: Path, monkeypatch, capsys) -> None:
    bundle_dir = tmp_path / "bundle"
    seen = {}

    def fake_export_recap_bundle(**kwargs):
        seen.update(kwargs)
        return bundle_dir

    monkeypatch.setattr(recap_export, "export_recap_bundle", fake_export_recap_bundle)

    code = cli.main(["recap", "export", "--since", "24h", "--output-dir", str(bundle_dir)])
    stdout = capsys.readouterr().out

    assert code == 0
    assert seen == {"since": "24h", "output_dir": str(bundle_dir)}
    assert str(bundle_dir) in stdout
