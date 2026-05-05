#!/usr/bin/env python3
"""Validate Hermes Pet sprite manifest frame references."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    manifest_path = repo / "overlay" / "assets" / "manifest.json"
    sprites_dir = repo / "overlay" / "assets" / "sprites"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    for species, species_config in sorted(manifest.get("species", {}).items()):
        states = species_config.get("states", {})
        for state, state_config in sorted(states.items()):
            asset_dir = state_config.get("assetDir")
            state_dir = sprites_dir / species / (asset_dir or state)
            frames = state_config.get("frames", [])
            for frame in frames:
                frame_path = state_dir / frame
                if not frame_path.exists():
                    errors.append(f"missing: {frame_path.relative_to(repo)}")
                elif frame_path.suffix.lower() != ".png":
                    errors.append(f"not png: {frame_path.relative_to(repo)}")

    if errors:
        print("Sprite manifest validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    species_count = len(manifest.get("species", {}))
    state_count = sum(
        len(species_config.get("states", {}))
        for species_config in manifest.get("species", {}).values()
    )
    print(f"Sprite manifest validation passed: {species_count} species, {state_count} species-state entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
