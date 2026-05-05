#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

python_bin="${PYTHON:-python3}"
venv_dir="$tmp_dir/venv"
home_dir="$tmp_dir/hermes-home"

"$python_bin" -m venv "$venv_dir"
# shellcheck disable=SC1091
source "$venv_dir/bin/activate"

python -m pip install --upgrade pip >/dev/null
python -m pip install --no-deps "$repo_root" >/dev/null

export HERMES_PET_HOME="$home_dir"
export HERMES_PET_FORCE_PACKAGED_OVERLAY=1

python - <<'PY'
from pathlib import Path

from hermes_pet import cli

overlay_dir = cli._overlay_dir()
required = cli._overlay_required_files()
missing = [rel for rel in required if not (overlay_dir / rel).is_file()]
sprites = overlay_dir / "assets" / "sprites"

if missing:
    raise SystemExit(f"missing packaged overlay files: {missing}")
if not sprites.is_dir() or not any(sprites.rglob("*.png")):
    raise SystemExit(f"packaged overlay sprites missing: {sprites}")
if "site-packages" not in str(Path(cli.__file__).resolve()):
    raise SystemExit(f"expected non-editable site-packages install, got {cli.__file__}")
if not overlay_dir.is_dir():
    raise SystemExit(f"overlay dir is not a directory: {overlay_dir}")

print(f"packaged overlay ok: {overlay_dir}")
PY
