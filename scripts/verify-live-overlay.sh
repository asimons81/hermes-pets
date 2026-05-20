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
custom_src="$tmp_dir/custom-pet"
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
mkdir -p "$home_dir" "$custom_src/sprites/idle"
cp "$repo_root/overlay/assets/sprites/cat/idle/idle_00.png" "$custom_src/sprites/idle/idle_00.png"

echo '{"name":"live-overlay-fallback","version":1,"states":{"idle":{"fps":1,"loop":true,"frames":["idle_00.png"]}}}' \
  > "$custom_src/custom-pet.json"

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
deadline = time.monotonic() + 20
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

run_cli custom-pet import "$custom_src" --name live-overlay-fallback >/dev/null
run_cli custom-pet use live-overlay-fallback >/dev/null

HERMES_PET_PORT="$port" \
HERMES_PET_DEBUG_EVENTS=1 \
HERMES_PET_OVERLAY_VERIFY_FILE="$verify_log_windows" \
HERMES_PET_ELECTRON_USER_DATA="$user_data_windows" \
HERMES_PET_POSITION_FILE="$position_file" \
"$python_bin" -m hermes_pet.cli launch --replace

wait_for_log "overlay ready" 'r.get("type") == "ready-to-show"'
wait_for_log "bridge connected" 'r.get("type") == "bridge-connected" and r.get("connected") is True'
run_cli custom-pet use live-overlay-fallback >/dev/null
wait_for_log "custom pet state event forwarded" 'r.get("type") == "pet-event" and r.get("hasCustomPet") is True and r.get("eventType") in ("state", "custom_pet")'
wait_for_log "custom pet fallback loaded" 'r.get("type") == "renderer-snapshot" and r.get("snapshot", {}).get("customPet") == "live-overlay-fallback" and r.get("snapshot", {}).get("animation") == "idle"'

run_cli emit job_finished "live overlay verifier success event" >/dev/null
wait_for_log "success event forwarded" 'r.get("type") == "pet-event" and r.get("eventType") == "job_finished" and r.get("severity") == "success"'

run_cli emit job_failed "live overlay verifier failure event" >/dev/null
wait_for_log "failure event forwarded" 'r.get("type") == "pet-event" and r.get("eventType") == "job_failed" and r.get("severity") == "error"'

run_cli emit approval_needed "live overlay verifier attention event" >/dev/null
wait_for_log "attention event forwarded" 'r.get("type") == "pet-event" and r.get("eventType") == "approval_needed" and r.get("severity") == "warning"'
wait_for_log "attention tray visible" 'r.get("type") == "renderer-snapshot" and r.get("snapshot", {}).get("trayAttention") is True'

before_bridge_stop_lines="$(log_line_count)"
"$python_bin" - "$port" <<'PY'
import sys
from hermes_pet import cli

stopped = cli._stop_bridge_processes(int(sys.argv[1]))
print(f"bridge stop for reconnect: {stopped}")
PY

wait_for_log "bridge disconnected" 'r.get("type") == "bridge-connected" and r.get("connected") is False' "$before_bridge_stop_lines"
before_bridge_restart_lines="$(log_line_count)"
HERMES_PET_PORT="$port" "$python_bin" -m hermes_pet.bridge --serve --port "$port" >/dev/null 2>&1 &
bridge_pid=$!
wait_for_log "bridge reconnected" 'r.get("type") == "bridge-connected" and r.get("connected") is True' "$before_bridge_restart_lines"

run_cli close --bridge
wait "$bridge_pid" 2>/dev/null || true

echo "live overlay verifier: passed"
