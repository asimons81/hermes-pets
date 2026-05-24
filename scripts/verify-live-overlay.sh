#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON:-python3}"

is_wsl=false
if [[ -r /proc/version ]] && grep -qi microsoft /proc/version; then
  is_wsl=true
fi

if [[ "$is_wsl" != true ]]; then
  echo "skip: live Windows overlay verification requires WSL with Windows interop."
  exit 0
fi

if ! command -v powershell.exe >/dev/null 2>&1; then
  echo "skip: powershell.exe is not available from WSL."
  exit 0
fi

if ! command -v wslpath >/dev/null 2>&1; then
  echo "skip: wslpath is not available from WSL."
  exit 0
fi

if [[ -z "${HERMES_PET_LIVE_OVERLAY_ATTEMPT:-}" ]]; then
  for attempt in 1 2 3; do
    echo "live overlay verifier: attempt $attempt/3"
    if HERMES_PET_LIVE_OVERLAY_ATTEMPT="$attempt" "$0"; then
      exit 0
    fi
    echo "live overlay verifier: attempt $attempt failed; cleaning up before retry" >&2
    "$python_bin" -m hermes_pet.cli close --bridge >/dev/null 2>&1 || true
    sleep 2
  done
  echo "failure: live overlay verifier failed after 3 attempts" >&2
  exit 1
fi

tmp_dir="$(mktemp -d)"
verify_dir="$tmp_dir"
if [[ -d /mnt/c/tmp && -w /mnt/c/tmp ]]; then
  verify_dir="$(mktemp -d /mnt/c/tmp/hermes-pet-live-overlay.XXXXXX)"
fi

home_dir="$tmp_dir/hermes-home"
verify_log="$verify_dir/overlay-verify.jsonl"
position_file="$tmp_dir/pet-position.json"
export HERMES_PET_HOME="$home_dir"
export PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}"

cleanup() {
  set +e
  HERMES_PET_PORT="${port:-}" "$python_bin" -m hermes_pet.cli close --bridge >/dev/null 2>&1
  rm -rf "$tmp_dir"
  if [[ "$verify_dir" == /mnt/c/tmp/hermes-pet-live-overlay.* ]]; then
    rm -rf "$verify_dir"
  fi
}
trap cleanup EXIT

port="$("$python_bin" - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"

verify_log_windows="$(wslpath -w "$verify_log")"
user_data_windows="$(wslpath -w "$verify_dir/electron-user-data")"
export WSLENV="HERMES_PET_OVERLAY_VERIFY_FILE:HERMES_PET_ELECTRON_USER_DATA:HERMES_PET_DEBUG_EVENTS${WSLENV:+:$WSLENV}"
run_cli() {
  HERMES_PET_PORT="$port" "$python_bin" -m hermes_pet.cli "$@"
}

wait_for_log() {
  local label="$1"
  local expr="$2"
  local start_line="${3:-0}"
  "$python_bin" - "$verify_log" "$label" "$expr" "$start_line" <<'PY'
import json
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
label = sys.argv[2]
expr = sys.argv[3]
start_line = int(sys.argv[4])
deadline = time.monotonic() + 45
records = []

while time.monotonic() < deadline:
    records = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    for rec in records[start_line:]:
        if eval(expr, {"__builtins__": {}}, {"r": rec}):
            print(f"ok: {label}")
            raise SystemExit(0)
    time.sleep(0.25)

print(f"failure: timed out waiting for {label}", file=sys.stderr)
print(f"verify log: {path}", file=sys.stderr)
for rec in records[-12:]:
    print(json.dumps(rec, sort_keys=True), file=sys.stderr)
raise SystemExit(1)
PY
}

log_line_count() {
  if [[ ! -f "$verify_log" ]]; then
    echo 0
    return
  fi
  wc -l < "$verify_log" | tr -d ' '
}

echo "live overlay verifier: temp HERMES_PET_HOME=$HERMES_PET_HOME"
echo "live overlay verifier: port=$port"

HERMES_PET_PORT="$port" \
HERMES_PET_DEBUG_EVENTS=1 \
HERMES_PET_OVERLAY_VERIFY_FILE="$verify_log_windows" \
HERMES_PET_ELECTRON_USER_DATA="$user_data_windows" \
HERMES_PET_POSITION_FILE="$position_file" \
"$python_bin" -m hermes_pet.cli launch --replace

wait_for_log "overlay ready" 'r.get("type") == "ready-to-show"'
status_after_launch="$(run_cli overlay-status)"
if [[ "$status_after_launch" != *"Overlay processes:"* ]]; then
  echo "failure: overlay status missing after launch" >&2
  printf '%s\n' "$status_after_launch" >&2
  exit 1
fi

before_replace_lines="$(log_line_count)"
HERMES_PET_PORT="$port" \
HERMES_PET_DEBUG_EVENTS=1 \
HERMES_PET_OVERLAY_VERIFY_FILE="$verify_log_windows" \
HERMES_PET_ELECTRON_USER_DATA="$user_data_windows" \
HERMES_PET_POSITION_FILE="$position_file" \
"$python_bin" -m hermes_pet.cli launch --replace
wait_for_log "overlay relaunched after replace" 'r.get("type") == "ready-to-show"' "$before_replace_lines"

status_after_replace="$(run_cli overlay-status)"
if [[ "$status_after_replace" != *"Overlay processes:"* ]]; then
  echo "failure: overlay status missing after replace" >&2
  printf '%s\n' "$status_after_replace" >&2
  exit 1
fi

run_cli close --bridge
status_after_close="$(run_cli overlay-status)"
if [[ "$status_after_close" != *"Overlay processes: none"* ]]; then
  echo "failure: overlay still running after close" >&2
  printf '%s\n' "$status_after_close" >&2
  exit 1
fi

echo "live overlay verifier: passed"
