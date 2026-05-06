#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
install_target="${HERMES_PET_INSTALL_TARGET:-git+https://github.com/asimons81/hermes-pets.git}"
work_dir="${HERMES_PET_INSTALL_SMOKE_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/hermes-pet-github-install.XXXXXX")}"
venv_dir="$work_dir/venv"
state_dir="$work_dir/state"

cleanup() {
  if [ "${HERMES_PET_KEEP_INSTALL_SMOKE:-0}" != "1" ]; then
    rm -rf "$work_dir"
  else
    echo "Preserving smoke directory: $work_dir"
  fi
}
trap cleanup EXIT

echo "== Hermes Pets GitHub install smoke =="
echo "Install target: $install_target"
echo "Work dir: $work_dir"

python3 -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --upgrade pip >/dev/null
"$venv_dir/bin/python" -m pip install "$install_target"

export HERMES_PET_HOME="$state_dir"
export HERMES_PET_FORCE_PACKAGED_OVERLAY=1
export HERMES_PET_PORT="${HERMES_PET_PORT:-18473}"
export PATH="$venv_dir/bin:$PATH"

echo
echo "== installed cli =="
hermes-pet --help >/dev/null
hermes-pet prefs
hermes-pet doctor

echo
echo "== package fixture validation =="
hermes-pet custom-pet validate "$repo_root/docs/fixtures/custom-pets/minimal-spark"

echo
echo "== wrapped command smoke =="
hermes-pet wrap --name "fresh install smoke" --status-interval 0 -- "$venv_dir/bin/python" -c "print('fresh install ok')"
hermes-pet jobs --last
hermes-pet brief --since 24h

echo
echo "Hermes Pets GitHub install smoke complete."
