#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON:-python3}"
tmp_dir=""
fresh_install=0
temp_state=0

usage() {
  cat <<'EOF'
Usage: scripts/smoke-hermes-pet.sh [--temp-state] [--fresh-install]

  --temp-state     Run against a temporary HERMES_PET_HOME and remove it on exit.
  --fresh-install  Create a temporary venv, install this repo, then run the smoke.
EOF
}

cleanup() {
  if [ -n "$tmp_dir" ]; then
    rm -rf "$tmp_dir"
  fi
}
trap cleanup EXIT

while [ "$#" -gt 0 ]; do
  case "$1" in
    --temp-state)
      temp_state=1
      ;;
    --fresh-install)
      fresh_install=1
      temp_state=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [ "$temp_state" -eq 1 ] || [ "$fresh_install" -eq 1 ]; then
  tmp_dir="$(mktemp -d)"
fi

if [ "$fresh_install" -eq 1 ]; then
  venv_dir="$tmp_dir/venv"
  "$python_bin" -m venv "$venv_dir"
  # shellcheck disable=SC1091
  source "$venv_dir/bin/activate"
  python -m pip install "$repo_root" >/dev/null
fi

if [ "$temp_state" -eq 1 ]; then
  export HERMES_PET_HOME="$tmp_dir/hermes-home"
  mkdir -p "$HERMES_PET_HOME"
fi

echo "== Hermes Pets smoke =="
if [ "$temp_state" -eq 1 ]; then
  echo "state: $HERMES_PET_HOME"
fi

if ! command -v hermes-pet >/dev/null 2>&1; then
  if PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}" "$python_bin" -m hermes_pet.cli --help >/dev/null 2>&1; then
    hermes_pet=(env PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}" "$python_bin" -m hermes_pet.cli)
  else
    echo "hermes-pet command not found on PATH" >&2
    exit 127
  fi
else
  hermes_pet=(hermes-pet)
fi

echo
echo "== update dry-run =="
"${hermes_pet[@]}" update --dry-run --no-install

echo
echo "== prefs =="
"${hermes_pet[@]}" prefs

echo
echo "== doctor =="
"${hermes_pet[@]}" doctor || true

echo
echo "== emit bubble =="
if ! "${hermes_pet[@]}" emit bubble "Hermes Pets smoke check"; then
  echo "emit failed; launch the overlay with: hermes-pet launch" >&2
fi

echo
echo "== wrapped success =="
"${hermes_pet[@]}" wrap --name "smoke success" -- bash -lc 'printf "%s\n" "smoke success"'

echo
echo "== wrapped failure =="
set +e
"${hermes_pet[@]}" wrap --name "smoke expected failure" -- bash -lc 'printf "%s\n" "smoke expected failure" >&2; exit 7'
failure_code=$?
set -e
if [ "$failure_code" -eq 7 ]; then
  echo "expected failure wrapper returned 7"
else
  echo "failure wrapper returned $failure_code (expected 7)" >&2
fi

echo
echo "== jobs --last =="
"${hermes_pet[@]}" jobs --last

echo
echo "== brief =="
"${hermes_pet[@]}" brief --since 24h

echo
echo "Hermes Pets smoke complete."
