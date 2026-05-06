import shutil

import pytest

from hermes_pet.custom_pets import inspect_package


def test_inspect_minimal_custom_pet_fixture() -> None:
    package = inspect_package("docs/fixtures/custom-pets/minimal-spark")

    assert package.name == "minimal-spark"
    assert package.source_format == "custom-pet"
    assert sorted(package.states) == ["idle"]
    assert package.states["idle"]["frames"] == ["idle_00.png"]


def test_custom_pet_requires_idle_state(tmp_path) -> None:
    bad_package = tmp_path / "bad-pet"
    waiting = bad_package / "sprites" / "waiting"
    waiting.mkdir(parents=True)
    shutil.copy2("docs/fixtures/custom-pets/minimal-spark/sprites/idle/idle_00.png", waiting / "waiting_00.png")

    with pytest.raises(ValueError, match="idle"):
        inspect_package(bad_package)
