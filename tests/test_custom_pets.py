import json
import shutil

import pytest
from PIL import Image

from hermes_pet import cli

from hermes_pet.custom_pets import (
    activate_custom_pet,
    clear_active_custom_pet,
    discover_codex_pet_candidates,
    import_codex_pet,
    import_package,
    inspect_package,
    custom_pet_preview_summary,
    render_custom_pet_preview_html,
    resolve_codex_pet_candidate,
)
from hermes_pet.engine import CUSTOM_PET_SPECIES, load_pet


def test_inspect_minimal_custom_pet_fixture() -> None:
    package = inspect_package("docs/fixtures/custom-pets/minimal-spark")

    assert package.name == "minimal-spark"
    assert package.source_format == "custom-pet"
    assert sorted(package.states) == ["idle"]
    assert package.states["idle"]["frames"] == ["idle_00.png"]


def test_inspect_basic_custom_pet_template() -> None:
    package = inspect_package("docs/templates/custom-pets/basic")

    assert package.name == "basic"
    assert package.source_format == "custom-pet"
    assert sorted(package.states) == ["idle"]


def test_custom_pet_preview_summary_reports_missing_optional_states() -> None:
    package = inspect_package("docs/fixtures/custom-pets/minimal-spark")
    summary = custom_pet_preview_summary(package)

    assert summary["name"] == "minimal-spark"
    assert summary["states"][0]["name"] == "idle"
    assert summary["states"][0]["frame_count"] == 1
    assert "failed" in summary["missing_optional_states"]
    assert summary["missing_fallback"] == "idle"


def test_custom_pet_preview_html_embeds_frames() -> None:
    package = inspect_package("docs/fixtures/custom-pets/minimal-spark")
    html = render_custom_pet_preview_html(package)

    assert "minimal-spark" in html
    assert "data:image/png;base64," in html
    assert "Missing optional states" in html


def test_custom_pet_requires_idle_state(tmp_path) -> None:
    bad_package = tmp_path / "bad-pet"
    waiting = bad_package / "sprites" / "waiting"
    waiting.mkdir(parents=True)
    shutil.copy2("docs/fixtures/custom-pets/minimal-spark/sprites/idle/idle_00.png", waiting / "waiting_00.png")

    with pytest.raises(ValueError, match="idle"):
        inspect_package(bad_package)


PNG_BYTES = b"\x89PNG\r\n\x1a\nminimal"


def _write_png(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_BYTES)


def _write_codex_spritesheet(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (1536, 1872), (255, 0, 255, 0)).save(path)


def _make_codex_package(repo_root, slug="spark"):
    package = repo_root / "output" / "hermes-pet-hatch" / slug / "package"
    _write_png(package / "sprites" / "idle" / "idle_00.png")
    (package / "custom-pet.json").write_text('{"name":"' + slug + '","source_format":"hatch-pet"}', encoding="utf-8")
    return package


def _make_codex_app_pet(codex_home, slug="ruby", *, spritesheet_path="spritesheet.webp"):
    pet = codex_home / "pets" / slug
    pet.mkdir(parents=True, exist_ok=True)
    _write_codex_spritesheet(pet / "spritesheet.webp")
    metadata = {"id": slug, "displayName": slug.title(), "spritesheetPath": spritesheet_path}
    (pet / "pet.json").write_text(json.dumps(metadata), encoding="utf-8")
    return pet


def _make_hatch_run(repo_root, slug="dragon"):
    run = repo_root / "output" / "hatch-pet-runs" / slug
    _write_png(run / "frames" / "idle" / "00.png")
    _write_png(run / "qa" / "contact-sheet.png")
    (run / "final").mkdir(parents=True, exist_ok=True)
    (run / "final" / "validation.json").write_text('{"errors":[]}', encoding="utf-8")
    return run


def test_discovers_codex_app_pets_first_and_resolves_latest(tmp_path, monkeypatch) -> None:
    codex_home = tmp_path / "codex-home"
    ruby = _make_codex_app_pet(codex_home, "ruby")
    _make_codex_package(tmp_path, "spark")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("HERMES_PET_DISABLE_WINDOWS_CODEX_SCAN", "1")

    candidates = discover_codex_pet_candidates(tmp_path)

    assert [candidate.slug for candidate in candidates] == ["ruby"]
    assert candidates[0].path == ruby.resolve()
    assert candidates[0].source_kind == "codex-pet"
    assert resolve_codex_pet_candidate("latest", repo=tmp_path).slug == "ruby"


def test_discovers_repo_output_only_when_requested(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing-codex-home"))
    monkeypatch.setenv("HERMES_PET_DISABLE_WINDOWS_CODEX_SCAN", "1")
    package = _make_codex_package(tmp_path, "spark")

    assert discover_codex_pet_candidates(tmp_path) == []
    candidates = discover_codex_pet_candidates(tmp_path, include_repo_output=True)

    assert [candidate.slug for candidate in candidates] == ["spark"]
    assert candidates[0].path == package.resolve()
    assert candidates[0].source_kind == "codex-package"



def test_activate_custom_pet_makes_it_the_active_pet(tmp_path) -> None:
    package = _make_codex_package(tmp_path, "spark")
    import_package(package, name="spark", base_dir=tmp_path)

    activated = activate_custom_pet("spark", base_dir=tmp_path)
    pet = load_pet("", state_dir=tmp_path)

    assert pet is not None
    assert pet.name == "spark"
    assert pet.species == CUSTOM_PET_SPECIES
    assert activated["custom_pet"]["name"] == "spark"
    assert "spark (Lv.1) [custom pet]" in pet.status_line()


def test_clear_active_custom_pet_removes_custom_only_pet_state(tmp_path) -> None:
    package = _make_codex_package(tmp_path, "spark")
    import_package(package, name="spark", base_dir=tmp_path)
    activate_custom_pet("spark", base_dir=tmp_path)

    assert clear_active_custom_pet(tmp_path) is True

    assert load_pet("", state_dir=tmp_path) is None

def test_import_codex_pet_from_packaged_output(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing-codex-home"))
    monkeypatch.setenv("HERMES_PET_DISABLE_WINDOWS_CODEX_SCAN", "1")
    _make_codex_package(tmp_path / "repo", "spark")
    state = tmp_path / "state"

    result = import_codex_pet("spark", repo=tmp_path / "repo", base_dir=state, name="operator-spark", include_repo_output=True)

    assert result["imported"]["name"] == "operator-spark"
    assert (state / "custom-pets" / "operator-spark" / "custom-pet.json").is_file()
    assert (state / "custom-pets" / "operator-spark" / "sprites" / "idle" / "idle_00.png").is_file()


def test_import_codex_pet_from_hatch_run_copies_contact_sheet(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing-codex-home"))
    monkeypatch.setenv("HERMES_PET_DISABLE_WINDOWS_CODEX_SCAN", "1")
    _make_hatch_run(tmp_path / "repo", "dragon")
    state = tmp_path / "state"

    result = import_codex_pet("dragon", repo=tmp_path / "repo", base_dir=state, include_repo_output=True)

    assert result["candidate"]["source_kind"] == "hatch-pet-run"
    installed = state / "custom-pets" / "dragon"
    assert (installed / "sprites" / "idle" / "idle_00.png").is_file()
    assert (installed / "contact-sheet.png").is_file()


def test_import_codex_app_pet_slices_spritesheet(tmp_path, monkeypatch) -> None:
    codex_home = tmp_path / "codex-home"
    _make_codex_app_pet(codex_home, "ruby")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("HERMES_PET_DISABLE_WINDOWS_CODEX_SCAN", "1")
    state = tmp_path / "state"

    result = import_codex_pet("ruby", base_dir=state)

    assert result["candidate"]["source_kind"] == "codex-pet"
    installed = state / "custom-pets" / "ruby"
    assert (installed / "custom-pet.json").is_file()
    assert (installed / "codex-pet.json").is_file()
    assert (installed / "spritesheet.webp").is_file()
    assert len(list((installed / "sprites" / "idle").glob("*.png"))) == 6
    assert len(list((installed / "sprites" / "run_right").glob("*.png"))) == 8


def _assert_codex_import_rejected(tmp_path, monkeypatch, spritesheet_path, message):
    codex_home = tmp_path / "codex-home"
    _make_codex_app_pet(codex_home, "escape", spritesheet_path=spritesheet_path)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("HERMES_PET_DISABLE_WINDOWS_CODEX_SCAN", "1")
    state = tmp_path / "state"

    with pytest.raises(ValueError, match=message):
        import_codex_pet("escape", base_dir=state)

    assert not (state / "custom-pets" / "escape").exists()


def test_codex_spritesheet_path_traversal_is_rejected(tmp_path, monkeypatch) -> None:
    outside = tmp_path / "codex-home" / "pets" / "outside.webp"
    _write_codex_spritesheet(outside)

    _assert_codex_import_rejected(tmp_path, monkeypatch, "../outside.webp", "traversal")


def test_codex_spritesheet_absolute_path_is_rejected(tmp_path, monkeypatch) -> None:
    outside = tmp_path / "outside.webp"
    _write_codex_spritesheet(outside)

    _assert_codex_import_rejected(tmp_path, monkeypatch, str(outside), "relative")


def test_codex_spritesheet_windows_drive_path_is_rejected(tmp_path, monkeypatch) -> None:
    _assert_codex_import_rejected(tmp_path, monkeypatch, r"C:\Users\Tony\outside.webp", "relative")


def test_codex_spritesheet_unc_path_is_rejected(tmp_path, monkeypatch) -> None:
    _assert_codex_import_rejected(tmp_path, monkeypatch, r"\\server\share\outside.webp", "relative")


def test_codex_spritesheet_symlink_escape_is_rejected(tmp_path, monkeypatch) -> None:
    codex_home = tmp_path / "codex-home"
    pet = _make_codex_app_pet(codex_home, "escape", spritesheet_path="link.webp")
    outside = tmp_path / "outside.webp"
    _write_codex_spritesheet(outside)
    try:
        (pet / "link.webp").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unsupported: {exc}")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("HERMES_PET_DISABLE_WINDOWS_CODEX_SCAN", "1")
    state = tmp_path / "state"

    with pytest.raises(ValueError, match="escapes"):
        import_codex_pet("escape", base_dir=state)

    assert not (state / "custom-pets" / "escape").exists()


def test_codex_pet_store_symlinked_pet_dir_escape_is_not_discovered(tmp_path, monkeypatch) -> None:
    codex_home = tmp_path / "codex-home"
    pets_dir = codex_home / "pets"
    pets_dir.mkdir(parents=True)
    outside_pet = _make_codex_app_pet(tmp_path / "outside-codex-home", "escape")
    try:
        (pets_dir / "escape").symlink_to(outside_pet, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink unsupported: {exc}")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("HERMES_PET_DISABLE_WINDOWS_CODEX_SCAN", "1")
    state = tmp_path / "state"

    assert discover_codex_pet_candidates() == []
    with pytest.raises(ValueError, match="No importable Codex pets found"):
        import_codex_pet("escape", base_dir=state)

    assert not (state / "custom-pets" / "escape").exists()


def test_codex_missing_spritesheet_fails_cleanly_and_cleans_partial_import(tmp_path, monkeypatch) -> None:
    _assert_codex_import_rejected(tmp_path, monkeypatch, "missing.webp", "missing Codex pet spritesheet")


def test_codex_bad_import_cli_exits_nonzero_without_traceback(tmp_path, monkeypatch, capsys) -> None:
    codex_home = tmp_path / "codex-home"
    outside = codex_home / "pets" / "outside.webp"
    _write_codex_spritesheet(outside)
    _make_codex_app_pet(codex_home, "escape", spritesheet_path="../outside.webp")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("HERMES_PET_DISABLE_WINDOWS_CODEX_SCAN", "1")
    monkeypatch.setenv("HERMES_PET_HOME", str(tmp_path / "state"))

    assert cli.main(["custom-pet", "import-codex", "escape"]) == 1

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Codex pet import failed" in captured.err
    assert "Traceback" not in combined
    assert not (tmp_path / "state" / "custom-pets" / "escape").exists()
