import shutil

import pytest

from hermes_pet.custom_pets import custom_pet_preview_summary, inspect_package, render_custom_pet_preview_html


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
