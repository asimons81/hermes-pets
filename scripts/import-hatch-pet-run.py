#!/usr/bin/env python3
"""Import a finalized hatch-pet run into Hermes Pet sprite assets."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


STATE_MAP = {
    "idle": ("idle", 4, True, None),
    "running-right": ("run_right", 9, True, None),
    "running-left": ("run_left", 9, True, None),
    "waving": ("waving", 8, False, "idle"),
    "jumping": ("jumping", 8, False, "idle"),
    "failed": ("failed", 7, False, "idle"),
    "waiting": ("waiting", 5, True, None),
    "running": ("running", 8, True, None),
    "review": ("review", 6, True, None),
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def numbered_frames(path: Path) -> list[Path]:
    return sorted(item for item in path.glob("*.png") if item.stem.isdigit())


def species_block(species: str, states: dict[str, dict]) -> str:
    block = json.dumps({species: {"states": states}}, indent=4)
    lines = block.splitlines()[1:-1]
    return "\n".join(lines)


def write_manifest(path: Path, manifest: dict, species: str, states: dict[str, dict]) -> None:
    original = path.read_text(encoding="utf-8")
    existing_species = manifest.get("species", {})
    if species not in existing_species:
        marker = "\n    }\n  }\n}\n"
        if original.endswith(marker):
            updated = original[: -len(marker)] + "\n    },\n" + species_block(species, states) + "\n  }\n}\n"
            path.write_text(updated, encoding="utf-8")
            return

    manifest.setdefault("species", {})[species] = {"states": states}
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--species", required=True)
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    repo = Path(args.repo_root).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    species = args.species.strip().lower()
    frames_root = run_dir / "frames"
    review = load_json(run_dir / "qa" / "review.json")
    validation = load_json(run_dir / "final" / "validation.json")
    if not review.get("ok"):
        raise SystemExit(f"refusing import because review failed: {run_dir / 'qa' / 'review.json'}")
    if validation.get("errors"):
        raise SystemExit(f"refusing import because atlas validation failed: {run_dir / 'final' / 'validation.json'}")

    manifest_path = repo / "overlay" / "assets" / "manifest.json"
    manifest = load_json(manifest_path)
    sprite_root = repo / "overlay" / "assets" / "sprites" / species
    sprite_root.mkdir(parents=True, exist_ok=True)

    species_states: dict[str, dict] = {}
    for hatch_state, (hermes_state, fps, loop, fallback) in STATE_MAP.items():
        source_dir = frames_root / hatch_state
        frames = numbered_frames(source_dir)
        if not frames:
            continue

        dest_dir = sprite_root / hermes_state
        dest_dir.mkdir(parents=True, exist_ok=True)
        frame_names: list[str] = []
        for index, frame in enumerate(frames):
            frame_name = f"{hermes_state}_{index:02d}.png"
            shutil.copy2(frame, dest_dir / frame_name)
            frame_names.append(frame_name)

        state_config: dict[str, object] = {
            "fps": fps,
            "loop": loop,
            "frames": frame_names,
        }
        if fallback:
            state_config["fallback"] = fallback
        species_states[hermes_state] = state_config

    if not species_states:
        raise SystemExit(f"no importable frames found under {frames_root}")

    write_manifest(manifest_path, manifest, species, species_states)

    print(f"Imported {species}: {len(species_states)} states into {sprite_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
