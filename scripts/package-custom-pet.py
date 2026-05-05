#!/usr/bin/env python3
"""Create a Hermes Pet custom pet package from built-in sprites or a hatch-pet run."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes_pet.custom_pets import STATE_MAP, inspect_package, validate_pet_name, write_package_metadata


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_state_dirs(source_root: Path, target_root: Path, states: dict[str, dict]) -> None:
    sprites_root = target_root / "sprites"
    for state in states:
        source_dir = source_root / state
        if not source_dir.is_dir():
            continue
        target_dir = sprites_root / state
        target_dir.mkdir(parents=True, exist_ok=True)
        for frame in sorted(source_dir.glob("*.png")):
            shutil.copy2(frame, target_dir / frame.name)


def package_builtin(repo: Path, species: str, name: str, dest: Path) -> None:
    manifest = _load_json(repo / "overlay" / "assets" / "manifest.json")
    states = manifest.get("species", {}).get(species, {}).get("states", {})
    if not states:
        raise SystemExit(f"unknown or non-animated built-in species: {species}")
    source_root = repo / "overlay" / "assets" / "sprites" / species
    dest.mkdir(parents=True, exist_ok=False)
    _copy_state_dirs(source_root, dest, states)
    package = inspect_package(dest, name=name)
    package.states = {state: dict(config) for state, config in states.items() if state in package.states}
    write_package_metadata(dest, package)


def package_source(source: Path, name: str, dest: Path) -> None:
    package = inspect_package(source, name=name)
    dest.mkdir(parents=True, exist_ok=False)
    sprites_root = dest / "sprites"
    source_state_dirs = []
    for base in (source / "sprites", source / "frames", source):
        if base.is_dir():
            source_state_dirs.extend(item for item in sorted(base.iterdir()) if item.is_dir())
    for source_dir in source_state_dirs:
        state = STATE_MAP.get(source_dir.name, (source_dir.name, 4, True, None))[0]
        if state not in package.states:
            continue
        config = package.states[state]
        target_dir = sprites_root / state
        target_dir.mkdir(parents=True, exist_ok=True)
        frame_names = []
        for index, frame in enumerate(sorted(source_dir.glob("*.png"))):
            target_name = frame.name if not frame.stem.isdigit() else f"{state}_{index:02d}.png"
            shutil.copy2(frame, target_dir / target_name)
            frame_names.append(target_name)
        config["frames"] = frame_names
    write_package_metadata(dest, package)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Custom pet package name.")
    parser.add_argument("--source", help="Existing package, hatch-pet run, or sprites folder.")
    parser.add_argument("--builtin-species", help="Export an existing built-in animated species.")
    parser.add_argument("--output", required=True, help="Destination package directory.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1], help="Hermes Pet repo root.")
    args = parser.parse_args()

    name = validate_pet_name(args.name)
    repo = Path(args.repo_root).expanduser().resolve()
    dest = Path(args.output).expanduser().resolve()
    if dest.exists():
        raise SystemExit(f"output already exists: {dest}")

    if args.builtin_species:
        package_builtin(repo, args.builtin_species.strip().lower(), name, dest)
    elif args.source:
        package_source(Path(args.source).expanduser().resolve(), name, dest)
    else:
        raise SystemExit("provide --source or --builtin-species")

    print(f"Created custom pet package: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
