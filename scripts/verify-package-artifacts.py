#!/usr/bin/env python3
"""Build and inspect Hermes Pets wheel/sdist artifacts."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import os
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


REQUIRED_WHEEL_FILES = [
    "hermes_pet/cli.py",
    "hermes_pet/bridge.py",
    "hermes_pet/achievements.py",
    "hermes_pet/dashboard.py",
    "hermes_pet/voice.py",
    "hermes_pet/dashboard/index.html",
    "hermes_pet/dashboard/app.css",
    "hermes_pet/dashboard/app.js",
    "hermes_pet/overlay/package.json",
    "hermes_pet/overlay/src/main.js",
    "hermes_pet/overlay/src/main.windows.js",
    "hermes_pet/overlay/src/preload.js",
    "hermes_pet/overlay/src/renderer.js",
    "hermes_pet/overlay/src/renderer.html",
    "hermes_pet/overlay/src/renderer.css",
    "hermes_pet/overlay/assets/manifest.json",
    "hermes_pet/overlay/scripts/launch-windows-overlay.ps1",
]

REQUIRED_SDIST_SUFFIXES = [
    "/pyproject.toml",
    "/README.md",
    "/src/hermes_pet/cli.py",
    "/src/hermes_pet/bridge.py",
    "/src/hermes_pet/achievements.py",
    "/src/hermes_pet/dashboard.py",
    "/src/hermes_pet/voice.py",
    "/src/hermes_pet/dashboard/index.html",
    "/src/hermes_pet/dashboard/app.css",
    "/src/hermes_pet/dashboard/app.js",
    "/src/hermes_pet/overlay/package.json",
    "/src/hermes_pet/overlay/src/main.js",
    "/src/hermes_pet/overlay/src/main.windows.js",
    "/src/hermes_pet/overlay/src/preload.js",
    "/src/hermes_pet/overlay/src/renderer.js",
    "/src/hermes_pet/overlay/src/renderer.html",
    "/src/hermes_pet/overlay/src/renderer.css",
    "/src/hermes_pet/overlay/assets/manifest.json",
    "/src/hermes_pet/overlay/scripts/launch-windows-overlay.ps1",
]


def one_artifact(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise SystemExit(
            f"expected exactly one {pattern} in {directory}, found {len(matches)}"
        )
    return matches[0]


def require_all(names: set[str], required: list[str], label: str) -> None:
    missing = [name for name in required if name not in names]
    if missing:
        raise SystemExit(f"{label} missing required files: {missing}")


def require_suffixes(names: set[str], suffixes: list[str], label: str) -> None:
    missing = [
        suffix
        for suffix in suffixes
        if not any(name.endswith(suffix) for name in names)
    ]
    if missing:
        raise SystemExit(f"{label} missing required paths: {missing}")


def verify_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())

    require_all(names, REQUIRED_WHEEL_FILES, path.name)

    if not any(
        name.startswith("hermes_pet/overlay/assets/sprites/") and name.endswith(".png")
        for name in names
    ):
        raise SystemExit(f"{path.name} has no packaged overlay sprite PNGs")

    if not any(name.endswith(".dist-info/METADATA") for name in names):
        raise SystemExit(f"{path.name} missing wheel metadata")
    if not any(name.endswith(".dist-info/entry_points.txt") for name in names):
        raise SystemExit(f"{path.name} missing console script entry points")

    print(f"wheel artifact ok: {path}")


def verify_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        names = set(archive.getnames())

    require_suffixes(names, REQUIRED_SDIST_SUFFIXES, path.name)

    if not any(
        "/src/hermes_pet/overlay/assets/sprites/" in name and name.endswith(".png")
        for name in names
    ):
        raise SystemExit(f"{path.name} has no source overlay sprite PNGs")

    print(f"sdist artifact ok: {path}")


def build_with_log(label: str, callback, *args) -> str:
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            return callback(*args)
    except Exception:
        print(f"{label} failed; build log follows:", file=sys.stderr)
        print(log.getvalue(), file=sys.stderr)
        raise


def build_artifacts(repo_root: Path, out_dir: Path) -> tuple[Path, Path]:
    wheel_dir = out_dir / "wheel"
    sdist_dir = out_dir / "sdist"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    sdist_dir.mkdir(parents=True, exist_ok=True)

    backend = importlib.import_module("setuptools.build_meta")
    old_cwd = Path.cwd()
    try:
        os.chdir(repo_root)
        print(f"+ setuptools.build_meta.build_wheel {wheel_dir}")
        wheel_name = build_with_log("wheel build", backend.build_wheel, str(wheel_dir))
        print(f"+ setuptools.build_meta.build_sdist {sdist_dir}")
        sdist_name = build_with_log("sdist build", backend.build_sdist, str(sdist_dir))
    finally:
        os.chdir(old_cwd)

    return wheel_dir / wheel_name, sdist_dir / sdist_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and verify Hermes Pets wheel/sdist artifact contents."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Directory for built artifacts. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep the temporary artifact directory and print its path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    if args.out_dir:
        out_dir = args.out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        cleanup_dir = None
    else:
        cleanup_dir = Path(tempfile.mkdtemp(prefix="hermes-pet-artifacts."))
        out_dir = cleanup_dir

    try:
        wheel, sdist = build_artifacts(repo_root, out_dir)
        verify_wheel(wheel)
        verify_sdist(sdist)
        print(f"package artifacts ok: {out_dir}")
        if cleanup_dir and args.keep_artifacts:
            cleanup_dir = None
            print(f"kept artifacts: {out_dir}")
    finally:
        if cleanup_dir:
            shutil.rmtree(cleanup_dir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
