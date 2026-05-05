"""Standalone argparse CLI for Hermes Pet.

Commands:
- bare ``hermes-pet``: hatch if needed, otherwise show status
- ``status``: show full status and stats
- ``hatch``: re-roll a new pet
- ``rename <name>``: rename the current pet
- ``feed`` / ``pet`` / ``play``: interact for XP
- ``species``: list all species metadata
- ``delete``: release the current pet
- ``launch``: start the bridge and launch the Electron overlay
- ``custom <path>``: copy a custom PNG sprite into the pet state directory
- ``message``: emit a local external-message notification
- ``run -- <command>`` / ``wrap --name <name> -- <command>``: emit job
  lifecycle events around a local command
"""

from __future__ import annotations

import argparse
import importlib
import locale
import os
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from hermes_pet.engine import (
    Pet,
    delete_pet,
    gacha_rarity_table,
    get_all_species_info,
    load_pet,
    save_pet,
)
from hermes_pet.event_log import append_event, load_events
from hermes_pet.events import EVENT_TYPES, PetEventError, build_event
from hermes_pet.jobs import (
    OUTPUT_SUMMARY_LIMIT,
    append_job,
    jobs_path,
    latest_failed_job,
    new_job_id,
    recent_jobs,
    redact_command,
    redact_text,
    utc_now_iso,
)
from hermes_pet.prefs import QUIET_MODES, load_prefs, mute_for, prefs_path, save_prefs, set_quiet_mode

RARITY_ORDER = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
}


class PetCLIError(RuntimeError):
    """User-facing CLI error."""


def _state_dir() -> Path:
    return Path(os.environ.get("HERMES_PET_HOME") or "~/.hermes_pet").expanduser()


def _pet_path() -> Path:
    return _state_dir() / "pet.json"


def _custom_sprite_path() -> Path:
    return _state_dir() / "custom.png"


def _overlay_position_path() -> Path:
    return _state_dir() / "overlay-position.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _overlay_dir() -> Path:
    return _repo_root() / "overlay"


def _load_pet() -> Pet | None:
    return load_pet("", state_dir=_state_dir())


def _save_pet(pet: Pet) -> None:
    save_pet(pet, state_dir=_state_dir())


def _delete_pet_state() -> None:
    delete_pet(state_dir=_state_dir())


def _require_pet() -> Pet:
    pet = _load_pet()
    if pet is None:
        raise PetCLIError("No pet exists yet. Run 'hermes-pet hatch' first.")
    return pet


def _print_error(message: str) -> None:
    print(f"❌ {message}", file=sys.stderr)


def _print_pet_card(pet: Pet) -> None:
    print(pet.full_status())


def _pet_mutation(action: str, verb: str, fn: Callable[[Pet], list[str]]) -> int:
    pet = _require_pet()
    before_xp = pet.xp
    milestones = fn(pet)
    _save_pet(pet)
    delta_xp = pet.xp - before_xp
    print(f"{action} {verb} {pet.name}! +{delta_xp} XP")
    for milestone in milestones:
        print(f"  ✨ {milestone}")
    print()
    _print_pet_card(pet)
    return 0


def _cmd_bare(_: argparse.Namespace) -> int:
    pet = _load_pet()
    if pet is None:
        pet = Pet.hatch(profile_name="", force_seed=secrets.randbits(64))
        _save_pet(pet)
        print("🥚 A new pet has hatched!")
        print()
        _print_pet_card(pet)
        return 0

    print("🐾 Your pet is here.")
    print()
    _print_pet_card(pet)
    return 0


def _cmd_status(_: argparse.Namespace) -> int:
    pet = _load_pet()
    if pet is None:
        print("🐣 No pet yet. Run 'hermes-pet hatch' to summon one.")
        return 0

    print("🐾 Pet status")
    print()
    _print_pet_card(pet)
    return 0


def _cmd_hatch(_: argparse.Namespace) -> int:
    pet = Pet.hatch(profile_name="", force_seed=secrets.randbits(64))
    _save_pet(pet)
    print("🥚 New pet hatched!")
    print()
    _print_pet_card(pet)
    return 0


def _cmd_rename(args: argparse.Namespace) -> int:
    pet = _require_pet()
    new_name = " ".join(args.name).strip()
    if not new_name:
        raise PetCLIError("Name cannot be empty.")
    old_name = pet.name
    pet.name = new_name
    _save_pet(pet)
    print(f"✏️ Renamed {old_name} → {pet.name}")
    print()
    _print_pet_card(pet)
    return 0


def _cmd_feed(_: argparse.Namespace) -> int:
    return _pet_mutation("🍖", "Fed", lambda pet: pet.feed())


def _cmd_pet(_: argparse.Namespace) -> int:
    return _pet_mutation("🫳", "Petted", lambda pet: pet.pet())


def _cmd_play(_: argparse.Namespace) -> int:
    return _pet_mutation("🎾", "Played with", lambda pet: pet.play())


def _cmd_species(_: argparse.Namespace) -> int:
    species = sorted(
        get_all_species_info(),
        key=lambda item: (RARITY_ORDER.get(str(item.get("rarity")), 99), str(item.get("name", ""))),
    )
    odds = gacha_rarity_table()

    print("📚 Available species")
    print()
    for info in species:
        name = info.get("name", "unknown")
        rarity = info.get("rarity", "unknown")
        personality = info.get("personality", "")
        line = f"• {name} — {rarity} — {personality}"
        print(line)

    print()
    print("🎲 Gacha rarity odds")
    for rarity in ("common", "uncommon", "rare", "epic", "legendary"):
        if rarity in odds:
            print(f"• {rarity}: {odds[rarity]:.1f}%")
    return 0


def _cmd_delete(_: argparse.Namespace) -> int:
    pet = _load_pet()
    if pet is None:
        print("🫥 No pet to release.")
        return 0

    _delete_pet_state()
    print(f"🫥 Released {pet.name}.")
    return 0


def _is_wsl() -> bool:
    if sys.platform != "linux":
        return False
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return False


def _wsl_to_windows_path(path: Path) -> str:
    if not _is_wsl():
        return str(path)
    try:
        result = subprocess.run(
            ["wslpath", "-w", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        converted = result.stdout.strip()
        if converted:
            return converted
    except Exception:
        pass
    return str(path)


def _detached_popen_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        flags = 0
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        if flags:
            kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _resolve_bridge_port(bridge_mod) -> int:
    default_port = int(getattr(bridge_mod, "PET_BRIDGE_DEFAULT_PORT", 17473))
    raw = os.environ.get("HERMES_PET_PORT")
    if not raw:
        return default_port
    try:
        return int(raw)
    except ValueError:
        return default_port


def _start_bridge_process(port: int) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["HERMES_PET_PORT"] = str(port)
    env.setdefault("HERMES_PET_HOST", "127.0.0.1")
    cmd = [sys.executable, "-m", "hermes_pet.bridge", "--serve", "--port", str(port)]
    return subprocess.Popen(cmd, cwd=str(_repo_root()), env=env, **_detached_popen_kwargs())


def _wait_for_bridge(bridge_mod, port: int, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if bridge_mod.is_bridge_available(port=port, host="127.0.0.1"):
            return True
        time.sleep(0.1)
    return bridge_mod.is_bridge_available(port=port, host="127.0.0.1")


def _launch_bridge_and_overlay(args: argparse.Namespace) -> int:
    bridge_mod = importlib.import_module("hermes_pet.bridge")
    port = _resolve_bridge_port(bridge_mod)
    host = "127.0.0.1"
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    position_file = _overlay_position_path()

    if bridge_mod.is_bridge_available(port=port, host=host):
        print(f"🌉 Bridge already available on ws://{host}:{port}")
    else:
        print(f"🌉 Starting bridge on ws://{host}:{port}...")
        bridge_proc: subprocess.Popen[bytes] | None = None
        try:
            bridge_proc = _start_bridge_process(port)
        except Exception as exc:
            print(f"⚠️ Could not start bridge process: {exc}")
        else:
            if _wait_for_bridge(bridge_mod, port):
                print(f"✅ Bridge ready on ws://{host}:{port}")
            else:
                code = bridge_proc.poll()
                if code is None:
                    print("⚠️ Bridge did not become ready yet, but the process is still running.")
                else:
                    print(f"⚠️ Bridge exited with code {code}; overlay will still be launched.")

    overlay_dir = _overlay_dir()
    env = os.environ.copy()
    env["HERMES_PET_PORT"] = str(port)
    env["HERMES_PET_WS_URL"] = f"ws://{host}:{port}"
    env["HERMES_PET_POSITION_FILE"] = str(position_file)

    if _is_wsl() or sys.platform == "win32":
        script = overlay_dir / "scripts" / "launch-windows-overlay.ps1"
        if script.exists():
            launcher = None
            launcher_candidates = ("powershell.exe",) if _is_wsl() else ("powershell.exe", "pwsh", "powershell")
            for candidate in launcher_candidates:
                if shutil.which(candidate):
                    launcher = candidate
                    break

            if launcher:
                cmd = [
                    launcher,
                    "-NoLogo",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    _wsl_to_windows_path(script),
                    "-RepoPath",
                    _wsl_to_windows_path(overlay_dir),
                    "-Port",
                    str(port),
                    "-PositionFile",
                    _wsl_to_windows_path(position_file),
                ]
                if getattr(args, "replace", False):
                    cmd.append("-Replace")
                try:
                    result = subprocess.run(cmd, cwd=str(_repo_root()), env=env, capture_output=True, text=True)
                except Exception as exc:
                    print(f"⚠️ PowerShell launcher failed: {exc}")
                else:
                    if result.stdout:
                        print(result.stdout, end="")
                    if result.stderr:
                        print(result.stderr, end="", file=sys.stderr)
                    if result.returncode == 0:
                        return 0
                    print(f"⚠️ PowerShell launcher exited with code {result.returncode}; falling back to local Electron launch.")
            else:
                print("⚠️ PowerShell launcher not found; falling back to local Electron launch.")
        else:
            print("⚠️ Windows launcher script not found; falling back to local Electron launch.")

    electron_bin = shutil.which("electron")
    npx_bin = shutil.which("npx")
    candidates: list[list[str]] = []
    if electron_bin:
        candidates.append([electron_bin, "src/main.js"])
    if npx_bin:
        candidates.append([npx_bin, "electron", "src/main.js"])

    last_error: Exception | None = None
    for cmd in candidates:
        try:
            subprocess.Popen(cmd, cwd=str(overlay_dir), env=env, **_detached_popen_kwargs())
            print("🪟 Overlay launch requested.")
            return 0
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise PetCLIError(f"Could not launch Electron overlay: {last_error}")
    raise PetCLIError("Could not launch Electron overlay: neither 'electron' nor 'npx' was found.")


def _powershell_launcher() -> str | None:
    launcher_candidates = ("powershell.exe",) if _is_wsl() else ("powershell.exe", "pwsh", "powershell")
    for candidate in launcher_candidates:
        if shutil.which(candidate):
            return candidate
    return None


def _overlay_launcher_script() -> Path:
    return _overlay_dir() / "scripts" / "launch-windows-overlay.ps1"


def _run_overlay_launcher(*, port: int, mode: str) -> subprocess.CompletedProcess[str]:
    if not (_is_wsl() or sys.platform == "win32"):
        raise PetCLIError("Windows overlay process control is only available from Windows/WSL.")

    script = _overlay_launcher_script()
    if not script.exists():
        raise PetCLIError("Windows launcher script not found.")

    launcher = _powershell_launcher()
    if not launcher:
        raise PetCLIError("PowerShell launcher not found.")

    cmd = [
        launcher,
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        _wsl_to_windows_path(script),
        "-RepoPath",
        _wsl_to_windows_path(_overlay_dir()),
        "-Port",
        str(port),
    ]
    if mode == "status":
        cmd.append("-Status")
    elif mode == "stop":
        cmd.append("-Stop")
    else:
        raise PetCLIError(f"Unsupported overlay launcher mode: {mode}")

    try:
        return subprocess.run(cmd, cwd=str(_repo_root()), capture_output=True, text=True)
    except Exception as exc:
        raise PetCLIError(f"Overlay process control failed: {exc}") from exc


def _print_completed_process(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def _cmd_overlay_status(_: argparse.Namespace) -> int:
    bridge_mod = importlib.import_module("hermes_pet.bridge")
    port = _resolve_bridge_port(bridge_mod)
    host = "127.0.0.1"
    available = bridge_mod.is_bridge_available(port=port, host=host)
    print(f"Bridge: {'available' if available else 'unavailable'} at ws://{host}:{port}")

    try:
        result = _run_overlay_launcher(port=port, mode="status")
    except PetCLIError as exc:
        print(f"Overlay processes: {exc}")
        return 0

    _print_completed_process(result)
    if result.returncode != 0:
        print(f"Overlay processes: status check exited with code {result.returncode}")
    return 0


def _bridge_process_ids(port: int) -> list[int]:
    if os.name == "nt":
        return []

    try:
        result = subprocess.run(["ps", "-eo", "pid=,args="], check=True, capture_output=True, text=True)
    except Exception:
        return []

    current_pid = os.getpid()
    pids: list[int] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, args = stripped.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid == current_pid:
            continue
        if "hermes_pet.bridge" not in args or "--serve" not in args:
            continue
        if f"--port {port}" not in args and f"--port={port}" not in args:
            continue
        pids.append(pid)
    return pids


def _stop_bridge_processes(port: int) -> int:
    pids = _bridge_process_ids(port)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except OSError as exc:
            print(f"⚠️ Could not stop bridge process {pid}: {exc}", file=sys.stderr)

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        remaining = set(_bridge_process_ids(port)).intersection(pids)
        if not remaining:
            break
        time.sleep(0.1)

    remaining = set(_bridge_process_ids(port)).intersection(pids)
    for pid in sorted(remaining):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue
        except OSError as exc:
            print(f"⚠️ Could not force-stop bridge process {pid}: {exc}", file=sys.stderr)

    return len(pids)


def _cmd_close(args: argparse.Namespace) -> int:
    bridge_mod = importlib.import_module("hermes_pet.bridge")
    port = _resolve_bridge_port(bridge_mod)

    result = _run_overlay_launcher(port=port, mode="stop")
    _print_completed_process(result)
    if result.returncode != 0:
        print(f"Overlay close exited with code {result.returncode}")
        return result.returncode

    if getattr(args, "bridge", False):
        stopped = _stop_bridge_processes(port)
        if stopped:
            print(f"Stopped bridge process(es): {stopped}")
        else:
            print("Bridge processes: none")
    return 0


def _doctor_line(label: str, ok: bool, detail: str) -> bool:
    status = "ok" if ok else "warn"
    print(f"{status:4} {label}: {detail}")
    return ok


def _readable_json_file(path: Path, *, missing_ok: bool = False) -> tuple[bool, str]:
    if not path.exists():
        if missing_ok:
            return True, f"not present yet ({path})"
        return False, f"missing ({path})"
    if not path.is_file():
        return False, f"not a file ({path})"
    try:
        path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"not readable ({exc})"
    return True, str(path)


def _cmd_doctor(_: argparse.Namespace) -> int:
    bridge_mod = importlib.import_module("hermes_pet.bridge")
    port = _resolve_bridge_port(bridge_mod)
    host = os.environ.get("HERMES_PET_HOST") or "127.0.0.1"
    state_dir = _state_dir()
    overlay_dir = _overlay_dir()
    checks: list[bool] = []

    print("Hermes Pet doctor")
    checks.append(_doctor_line("python", bool(sys.executable), sys.executable or "not found"))

    cli_path = shutil.which("hermes-pet")
    checks.append(
        _doctor_line(
            "hermes-pet command",
            bool(cli_path),
            cli_path or "not on PATH; current module can still run as python -m hermes_pet.cli",
        )
    )

    checks.append(
        _doctor_line(
            "websockets package",
            bool(getattr(bridge_mod, "_WEBSOCKETS_AVAILABLE", False)),
            "available" if getattr(bridge_mod, "_WEBSOCKETS_AVAILABLE", False) else "missing; install package extras",
        )
    )
    checks.append(
        _doctor_line(
            "bridge",
            bridge_mod.is_bridge_available(port=port, host=host),
            f"ws://{host}:{port}",
        )
    )

    launcher = overlay_dir / "scripts" / "launch-windows-overlay.ps1"
    checks.append(_doctor_line("overlay dir", overlay_dir.is_dir(), str(overlay_dir)))
    checks.append(_doctor_line("overlay launcher", launcher.is_file(), str(launcher)))
    if not (_is_wsl() or sys.platform == "win32"):
        checks.append(_doctor_line("overlay-status", True, "Windows overlay process query not available on this OS"))
    elif not launcher.is_file():
        checks.append(_doctor_line("overlay-status", False, "launcher script missing"))
    else:
        ps_launcher = None
        ps_candidates = ("powershell.exe",) if _is_wsl() else ("powershell.exe", "pwsh", "powershell")
        for candidate in ps_candidates:
            if shutil.which(candidate):
                ps_launcher = candidate
                break
        if not ps_launcher:
            checks.append(_doctor_line("overlay-status", False, "PowerShell launcher not found"))
        else:
            status_cmd = [
                ps_launcher,
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                _wsl_to_windows_path(launcher),
                "-RepoPath",
                _wsl_to_windows_path(overlay_dir),
                "-Port",
                str(port),
                "-Status",
            ]
            try:
                status_result = subprocess.run(status_cmd, cwd=str(_repo_root()), capture_output=True, text=True, timeout=10)
            except Exception as exc:
                checks.append(_doctor_line("overlay-status", False, f"query failed: {exc}"))
            else:
                detail = _truncate_text((status_result.stdout or status_result.stderr or "query completed").strip(), 120)
                checks.append(_doctor_line("overlay-status", status_result.returncode == 0, detail))

    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        state_ok = state_dir.is_dir() and os.access(state_dir, os.R_OK | os.W_OK)
    except OSError:
        state_ok = False
    checks.append(_doctor_line("state dir", state_ok, str(state_dir)))

    try:
        prefs = load_prefs(state_dir)
        pref_ok = isinstance(prefs, dict)
        pref_detail = str(prefs_path(state_dir))
    except Exception as exc:
        pref_ok = False
        pref_detail = f"{prefs_path(state_dir)} ({exc})"
    checks.append(_doctor_line("prefs", pref_ok, pref_detail))

    job_ok, job_detail = _readable_json_file(jobs_path(state_dir), missing_ok=True)
    checks.append(_doctor_line("recent jobs", job_ok, job_detail))

    print()
    if all(checks):
        print("Doctor result: ready.")
        return 0
    print("Doctor result: warnings found. Use 'hermes-pet launch --replace' for duplicate or stale overlay issues.")
    return 0


def _cmd_custom(args: argparse.Namespace) -> int:
    src = Path(args.path).expanduser()
    if not src.is_file():
        raise PetCLIError(f"Custom sprite not found: {src}")

    dest = _custom_sprite_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    print(f"🖼️ Custom sprite saved to {dest}")
    return 0


def _send_pet_event(event_type: str, text: str, *, required: bool, **extra: object) -> tuple[bool, dict[str, object]]:
    try:
        event = build_event(event_type, text, **extra)
    except PetEventError as exc:
        raise PetCLIError(str(exc)) from exc

    try:
        append_event(event, base_dir=_state_dir())
    except Exception as exc:
        print(f"⚠️ Could not save event history: {exc}", file=sys.stderr)

    bridge_mod = importlib.import_module("hermes_pet.bridge")
    port = _resolve_bridge_port(bridge_mod)
    host = os.environ.get("HERMES_PET_HOST") or "127.0.0.1"
    bridge_url = os.environ.get("HERMES_PET_WS_URL")

    if not bridge_mod.send_event_to_bridge(event, port=port, host=host, bridge_url=bridge_url):
        if required:
            raise PetCLIError(
                f"Could not send event to ws://{host}:{port}. Run 'hermes-pet launch' first."
            )
        return False, event

    return True, event


def _cmd_emit(args: argparse.Namespace) -> int:
    event_type = str(args.event_type or "").strip().lower().replace("-", "_")
    text = " ".join(args.text).strip()
    _, event = _send_pet_event(event_type, text, required=True)

    print(f"📡 Emitted {event['type']}: {event['text']}")
    return 0


def _clean_message_field(value: object, *, field: str, limit: int = 80) -> str:
    text = _truncate_text(str(value or ""), limit)
    if not text:
        raise PetCLIError(f"{field} cannot be empty")
    return text


def _cmd_message(args: argparse.Namespace) -> int:
    source = _clean_message_field(args.source, field="source", limit=40).lower()
    sender = _clean_message_field(args.sender, field="sender", limit=80)
    message_text = _truncate_text(" ".join(args.text), 220)
    if not message_text:
        raise PetCLIError("message text cannot be empty")

    urgent = bool(getattr(args, "urgent", False))
    open_command = _truncate_text(str(getattr(args, "open_command", "") or ""), 220)
    extra: dict[str, object] = {
        "source": source,
        "sender": sender,
        "severity": "warning" if urgent else "info",
        "urgent": urgent,
    }
    if open_command:
        extra["open_command"] = open_command

    _, event = _send_pet_event("message_received", message_text, required=True, **extra)
    urgency = " urgent" if urgent else ""
    print(f"📨 Emitted{urgency} {event['source']} message from {event['sender']}: {event['text']}")
    return 0


def _notify_prefs_changed(prefs: dict[str, object]) -> bool:
    bridge_mod = importlib.import_module("hermes_pet.bridge")
    port = _resolve_bridge_port(bridge_mod)
    host = os.environ.get("HERMES_PET_HOST") or "127.0.0.1"
    bridge_url = os.environ.get("HERMES_PET_WS_URL")
    return bridge_mod.send_event_to_bridge(
        {"type": "notification_prefs", "prefs": prefs},
        port=port,
        host=host,
        bridge_url=bridge_url,
    )


def _parse_duration(value: str) -> timedelta:
    text = str(value or "").strip().lower()
    if not text:
        raise PetCLIError("duration cannot be empty")
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    suffix = text[-1]
    if suffix in units:
        number_text = text[:-1]
        scale = units[suffix]
    else:
        number_text = text
        scale = 60
    try:
        amount = float(number_text)
    except ValueError as exc:
        raise PetCLIError("duration must look like 30m, 2h, or 45s") from exc
    seconds = amount * scale
    if seconds <= 0:
        raise PetCLIError("duration must be greater than zero")
    return timedelta(seconds=seconds)


def _format_pref_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _print_prefs(prefs: dict[str, object]) -> None:
    print("Notification prefs")
    print(f"quiet_mode:              {_format_pref_value(prefs.get('quiet_mode'))}")
    print(f"muted_until:             {_format_pref_value(prefs.get('muted_until'))}")
    print(f"bubble_throttle_seconds: {_format_pref_value(prefs.get('bubble_throttle_seconds'))}")
    print(f"show_tray_on_urgent:     {_format_pref_value(prefs.get('show_tray_on_urgent'))}")
    print(f"show_idle_bubbles:       {_format_pref_value(prefs.get('show_idle_bubbles'))}")


def _cmd_quiet(args: argparse.Namespace) -> int:
    selected = "important"
    if getattr(args, "silent", False):
        selected = "silent"
    if getattr(args, "off", False):
        selected = "off"
    try:
        prefs = set_quiet_mode(selected, _state_dir())
    except ValueError as exc:
        raise PetCLIError(str(exc)) from exc
    _notify_prefs_changed(prefs)
    print(f"🔕 Quiet mode: {prefs['quiet_mode']}")
    return 0


def _cmd_mute(args: argparse.Namespace) -> int:
    try:
        prefs = mute_for(_parse_duration(args.duration), _state_dir())
    except ValueError as exc:
        raise PetCLIError(str(exc)) from exc
    _notify_prefs_changed(prefs)
    print(f"🔇 Muted non-urgent bubbles until {prefs['muted_until']}")
    return 0


def _coerce_pref_value(key: str, value: str) -> object:
    if key == "quiet_mode":
        mode = value.strip().lower()
        if mode not in QUIET_MODES:
            raise PetCLIError(f"quiet_mode must be one of: {', '.join(sorted(QUIET_MODES))}")
        return mode
    if key == "muted_until":
        return None if value.strip().lower() in {"", "-", "none", "null", "off"} else value.strip()
    if key == "bubble_throttle_seconds":
        try:
            return max(0.0, float(value))
        except ValueError as exc:
            raise PetCLIError("bubble_throttle_seconds must be a number") from exc
    if key in {"show_tray_on_urgent", "show_idle_bubbles"}:
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise PetCLIError(f"{key} must be true or false")
    raise PetCLIError(f"unknown preference {key!r}")


def _cmd_prefs(args: argparse.Namespace) -> int:
    if getattr(args, "prefs_action", None) == "set":
        prefs = load_prefs(_state_dir())
        key = str(args.key).strip()
        prefs[key] = _coerce_pref_value(key, str(args.value))
        prefs = save_prefs(prefs, _state_dir())
        _notify_prefs_changed(prefs)
        print(f"✅ Set {key}={_format_pref_value(prefs.get(key))}")
        return 0

    _print_prefs(load_prefs(_state_dir()))
    return 0


def _clean_command_remainder(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


def _raw_command_after_separator(args: argparse.Namespace) -> list[str]:
    raw_argv = list(getattr(args, "_raw_argv", []) or [])
    for subcommand in ("wrap", "run"):
        if subcommand not in raw_argv:
            continue
        tail = raw_argv[raw_argv.index(subcommand) + 1:]
        if "--" in tail:
            return tail[tail.index("--") + 1:]
    return []


def _single_line(value: str) -> str:
    return " ".join(str(value or "").split())


def _truncate_text(value: str, limit: int = 96) -> str:
    text = _single_line(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _format_duration(elapsed_s: float) -> str:
    total = max(0, int(round(elapsed_s)))
    if total < 60:
        return f"{total}s"
    minutes, seconds = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _infer_job_name(command: list[str]) -> str:
    if not command:
        return "command"
    preview_parts = [Path(str(command[0])).name or str(command[0])]
    for part in command[1:3]:
        if str(part).startswith("-") and len(preview_parts) > 1:
            break
        preview_parts.append(str(part))
    return _truncate_text(" ".join(preview_parts), 72)


class _OutputSummary:
    def __init__(self, limit: int = OUTPUT_SUMMARY_LIMIT) -> None:
        self.limit = limit
        self._tail = ""
        self._lock = threading.Lock()

    def add(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._tail = (self._tail + text)[-(self.limit * 2):]

    def summary(self) -> str:
        with self._lock:
            tail = self._tail
        return redact_text(tail, limit=self.limit)


def _capture_output_summary_enabled() -> bool:
    raw = os.environ.get("HERMES_PET_CAPTURE_OUTPUT")
    if raw is not None:
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return not (sys.stdout.isatty() and sys.stderr.isatty())


def _forward_stream(pipe, target, collector: _OutputSummary) -> None:
    try:
        for chunk in iter(pipe.readline, ""):
            if not chunk:
                break
            collector.add(chunk)
            target.write(chunk)
            target.flush()
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def _emit_job_event(event_type: str, text: str, *, warned: bool, **extra: object) -> bool:
    ok, _ = _send_pet_event(event_type, text, required=False, **extra)
    if not ok and not warned:
        print("⚠️ Pet bridge unavailable; running command without overlay events.", file=sys.stderr)
    return ok


def _record_job(
    *,
    job_id: str,
    name: str,
    command: list[str],
    command_redacted: bool,
    started_at: str,
    finished_at: str,
    exit_code: int,
    status: str,
    duration_s: float,
    output_summary: str = "",
    error_summary: str = "",
) -> None:
    job = {
        "id": job_id,
        "name": name,
        "command": command,
        "command_redacted": command_redacted,
        "retryable": not command_redacted,
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": int(exit_code),
        "status": status,
        "duration": round(max(0.0, duration_s), 3),
        "duration_text": _format_duration(duration_s),
    }
    if output_summary:
        job["output_summary"] = output_summary
    if error_summary:
        job["error_summary"] = error_summary

    try:
        append_job(job, base_dir=_state_dir())
    except Exception as exc:
        print(f"⚠️ Could not save job history: {exc}", file=sys.stderr)


def _command_display(command: object) -> str:
    if isinstance(command, list):
        return shlex.join([str(part) for part in command])
    return str(command or "")


def _job_duration_text(job: dict[str, object]) -> str:
    if job.get("duration_text"):
        return str(job["duration_text"])
    try:
        return _format_duration(float(job.get("duration", 0.0) or 0.0))
    except (TypeError, ValueError):
        return "-"


def _compact_time(value: object) -> str:
    text = str(value or "")
    if not text:
        return "-"
    return text.replace("T", " ").replace("Z", "")[:19]


def _print_jobs_table(jobs: list[dict[str, object]]) -> None:
    if not jobs:
        print("No job history yet.")
        return

    print(f"{'STARTED':19}  {'STATUS':9} {'DURATION':9} {'EXIT':>4}  NAME")
    for job in jobs:
        status = str(job.get("status") or "-")[:9]
        exit_code = job.get("exit_code")
        exit_text = "-" if exit_code is None else str(exit_code)
        name = _truncate_text(str(job.get("name") or "command"), 44)
        print(
            f"{_compact_time(job.get('started_at')):19}  "
            f"{status:9} {_job_duration_text(job):9} {exit_text:>4}  {name}"
        )


def _print_job_detail(job: dict[str, object] | None) -> None:
    if not job:
        print("No matching job history.")
        return

    command = _command_display(job.get("command"))
    if job.get("command_redacted"):
        command += "  [redacted]"

    print(f"ID:        {job.get('id', '-')}")
    print(f"Name:      {job.get('name', '-')}")
    print(f"Status:    {job.get('status', '-')}")
    print(f"Exit code: {job.get('exit_code', '-')}")
    print(f"Duration:  {_job_duration_text(job)}")
    print(f"Started:   {_compact_time(job.get('started_at'))}")
    print(f"Finished:  {_compact_time(job.get('finished_at'))}")
    print(f"Command:   {command}")
    if job.get("output_summary"):
        print(f"Output:    {job['output_summary']}")
    if job.get("error_summary"):
        print(f"Error:     {job['error_summary']}")
    if job.get("retryable") is False:
        print("Retry:     unavailable because the command contained sensitive-looking arguments")


def _parse_since_duration(value: str) -> timedelta:
    text = str(value or "").strip().lower()
    if len(text) < 2:
        raise PetCLIError("since must look like 30m, 2h, 24h, or 7d")
    suffix = text[-1]
    units = {"m": 60, "h": 3600, "d": 86400}
    if suffix not in units:
        raise PetCLIError("since must use m, h, or d, such as 30m, 2h, 24h, or 7d")
    try:
        amount = int(text[:-1])
    except ValueError as exc:
        raise PetCLIError("since must start with a whole number") from exc
    if amount <= 0:
        raise PetCLIError("since must be greater than zero")
    return timedelta(seconds=amount * units[suffix])


def _parse_iso_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _within_since(item: dict[str, object], cutoff: datetime) -> bool:
    for key in ("created_at", "finished_at", "started_at"):
        parsed = _parse_iso_time(item.get(key))
        if parsed is not None:
            return parsed >= cutoff
    return False


def _item_time(item: dict[str, object]) -> datetime:
    for key in ("created_at", "finished_at", "started_at"):
        parsed = _parse_iso_time(item.get(key))
        if parsed is not None:
            return parsed
    return datetime.min.replace(tzinfo=timezone.utc)


def _event_line(event: dict[str, object], *, limit: int = 90) -> str:
    event_type = str(event.get("type") or "event")
    text = _truncate_text(str(event.get("text") or ""), limit)
    if event_type == "message_received":
        source = str(event.get("source") or "message")
        sender = str(event.get("sender") or "someone")
        return _truncate_text(f"{source} from {sender}: {text}", limit)
    return _truncate_text(text or event_type, limit)


def _job_line(job: dict[str, object], *, limit: int = 90) -> str:
    name = _truncate_text(str(job.get("name") or "command"), 44)
    duration = _job_duration_text(job)
    exit_code = job.get("exit_code")
    exit_text = "" if exit_code in (None, 0) else f", exit {exit_code}"
    return _truncate_text(f"{name} ({duration}{exit_text})", limit)


def _build_brief(*, since: timedelta, telegram_text: bool = False) -> str:
    cutoff = datetime.now(timezone.utc) - since
    jobs = [job for job in recent_jobs(base_dir=_state_dir(), newest_first=True) if _within_since(job, cutoff)]
    indexed_events = [
        (index, event)
        for index, event in enumerate(load_events(_state_dir()))
        if _within_since(event, cutoff)
    ]
    indexed_events.sort(key=lambda item: (_item_time(item[1]), item[0]), reverse=True)
    events = [event for _, event in indexed_events]

    failures = [job for job in jobs if job.get("status") == "failed" or job.get("exit_code") not in (0, None)]
    successes = [job for job in jobs if job.get("status") == "succeeded" or job.get("exit_code") == 0]
    pending = [event for event in events if event.get("type") == "approval_needed"]
    messages = [event for event in events if event.get("type") == "message_received"]
    status_events = [event for event in events if event.get("type") in {"status", "job_started", "job_finished", "job_failed"}]

    latest_status = "No recent activity found."
    if status_events:
        latest_status = _event_line(status_events[0])
    elif jobs:
        latest_status = f"Latest job {jobs[0].get('status', 'finished')}: {_job_line(jobs[0])}"
    elif messages:
        latest_status = f"Latest message: {_event_line(messages[0])}"

    if pending:
        next_action = f"Review approval needed: {_event_line(pending[0], limit=70)}"
    elif failures:
        next_action = f"Retry or inspect latest failure: {_job_line(failures[0], limit=70)}"
    elif messages:
        next_action = f"Reply to latest message: {_event_line(messages[0], limit=70)}"
    elif successes:
        next_action = "No action needed; recent wrapped work is green."
    else:
        next_action = "Run work through hermes-pet wrap to build useful history."

    if telegram_text:
        parts = [
            f"Hermes brief ({_format_duration(since.total_seconds())})",
            f"Status: {latest_status}",
            f"Failures: {len(failures)}",
            f"Successes: {len(successes)}",
            f"Pending: {len(pending)}",
        ]
        if messages:
            parts.append(f"Msg: {_event_line(messages[0], limit=70)}")
        parts.append(f"Next: {next_action}")
        return "\n".join(parts)

    lines = [
        f"Hermes brief ({_format_duration(since.total_seconds())})",
        f"Latest status: {latest_status}",
    ]
    lines.append("Recent failures: " + ("none" if not failures else "; ".join(_job_line(job) for job in failures[:3])))
    lines.append("Recent successes: " + ("none" if not successes else "; ".join(_job_line(job) for job in successes[:3])))
    lines.append("Pending/approval-needed: " + ("none" if not pending else "; ".join(_event_line(event) for event in pending[:3])))
    lines.append("Recent messages: " + ("none" if not messages else "; ".join(_event_line(event) for event in messages[:3])))
    lines.append(f"Suggested next action: {next_action}")
    return "\n".join(lines)


def _cmd_brief(args: argparse.Namespace) -> int:
    since = _parse_since_duration(str(getattr(args, "since", "24h") or "24h"))
    telegram_text = bool(getattr(args, "telegram_text", False))
    summary = _build_brief(since=since, telegram_text=telegram_text)
    if getattr(args, "emit", False):
        ok, event = _send_pet_event("daily_brief", summary, required=False)
        if ok:
            print(f"📡 Emitted {event['type']}: {event['text']}")
        else:
            print("⚠️ Overlay unavailable; daily brief saved locally.")
            print(summary)
        return 0
    print(summary)
    return 0


def _cmd_jobs(args: argparse.Namespace) -> int:
    jobs = recent_jobs(
        base_dir=_state_dir(),
        failed_only=bool(getattr(args, "failed", False)),
        limit=max(1, int(getattr(args, "limit", 20) or 20)),
        newest_first=True,
    )
    if getattr(args, "last", False):
        _print_job_detail(jobs[0] if jobs else None)
        return 0

    _print_jobs_table(jobs)
    return 0


def _cmd_retry(args: argparse.Namespace) -> int:
    job = latest_failed_job(base_dir=_state_dir())
    if not job:
        raise PetCLIError("No failed wrapped job found.")
    if job.get("retryable") is False or job.get("command_redacted"):
        raise PetCLIError("Latest failed job has redacted sensitive arguments and cannot be retried safely.")
    command = job.get("command")
    if not isinstance(command, list) or not command:
        raise PetCLIError("Latest failed job does not have a retryable command.")

    clean_command = [str(part) for part in command]
    name = str(job.get("name") or _infer_job_name(clean_command))
    print(f"↻ Retrying {name}: {_command_display(clean_command)}")
    return _run_wrapped_command(
        clean_command,
        name=name,
        status_interval=max(0.0, float(getattr(args, "status_interval", 60.0) or 0.0)),
    )


def _run_wrapped_command(command: list[str], *, name: str, status_interval: float) -> int:
    if not command:
        raise PetCLIError("No command provided. Use: hermes-pet wrap --name \"Job\" -- <command>")

    job_name = _truncate_text(name.strip() if name.strip() else _infer_job_name(command), 96)
    job_id = new_job_id()
    started_at = utc_now_iso()
    redacted_command, command_redacted = redact_command(command)
    event_base = {
        "source": "hermes-pet.wrap",
        "job_id": job_id,
        "job_name": job_name,
        "command": redacted_command,
    }

    bridge_warned = False
    if not _emit_job_event("job_started", job_name, warned=bridge_warned, **event_base):
        bridge_warned = True

    start = time.monotonic()
    capture_summary = _capture_output_summary_enabled()
    stdout_summary = _OutputSummary()
    stderr_summary = _OutputSummary()
    output_threads: list[threading.Thread] = []
    try:
        if capture_summary:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding=locale.getpreferredencoding(False),
                errors="replace",
                bufsize=1,
            )
            if proc.stdout is not None:
                output_threads.append(
                    threading.Thread(
                        target=_forward_stream,
                        args=(proc.stdout, sys.stdout, stdout_summary),
                        daemon=True,
                    )
                )
            if proc.stderr is not None:
                output_threads.append(
                    threading.Thread(
                        target=_forward_stream,
                        args=(proc.stderr, sys.stderr, stderr_summary),
                        daemon=True,
                    )
                )
            for thread in output_threads:
                thread.start()
        else:
            proc = subprocess.Popen(command)
    except FileNotFoundError:
        elapsed = time.monotonic() - start
        finished_at = utc_now_iso()
        text = f"{job_name} could not start: command not found after {_format_duration(elapsed)}"
        _emit_job_event(
            "job_failed",
            text,
            warned=bridge_warned,
            exit_code=127,
            duration_s=round(elapsed, 3),
            **event_base,
        )
        _record_job(
            job_id=job_id,
            name=job_name,
            command=redacted_command,
            command_redacted=command_redacted,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=127,
            status="failed",
            duration_s=elapsed,
            error_summary=f"Command not found: {command[0]}",
        )
        print(f"❌ Command not found: {command[0]}", file=sys.stderr)
        return 127
    except OSError as exc:
        elapsed = time.monotonic() - start
        finished_at = utc_now_iso()
        text = f"{job_name} could not start after {_format_duration(elapsed)}: {exc}"
        _emit_job_event(
            "job_failed",
            _truncate_text(text),
            warned=bridge_warned,
            exit_code=126,
            duration_s=round(elapsed, 3),
            **event_base,
        )
        _record_job(
            job_id=job_id,
            name=job_name,
            command=redacted_command,
            command_redacted=command_redacted,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=126,
            status="failed",
            duration_s=elapsed,
            error_summary=str(exc),
        )
        print(f"❌ Could not start command: {exc}", file=sys.stderr)
        return 126

    last_status_text = ""
    next_status_at = start + status_interval if status_interval > 0 else float("inf")
    poll_interval = min(max(status_interval / 4, 0.25), 1.0) if status_interval > 0 else 1.0

    try:
        while True:
            try:
                return_code = proc.wait(timeout=poll_interval)
                break
            except subprocess.TimeoutExpired:
                if status_interval <= 0:
                    continue
                now = time.monotonic()
                if now >= next_status_at:
                    status_text = f"{job_name} still running ({_format_duration(now - start)})"
                    if status_text != last_status_text:
                        if not _emit_job_event(
                            "status",
                            status_text,
                            warned=bridge_warned,
                            duration_s=round(now - start, 3),
                            **event_base,
                        ):
                            bridge_warned = True
                        last_status_text = status_text
                    next_status_at = now + status_interval
    except KeyboardInterrupt:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        elapsed = time.monotonic() - start
        for thread in output_threads:
            thread.join(timeout=1.0)
        finished_at = utc_now_iso()
        _emit_job_event(
            "job_failed",
            f"{job_name} interrupted after {_format_duration(elapsed)}",
            warned=bridge_warned,
            exit_code=130,
            duration_s=round(elapsed, 3),
            **event_base,
        )
        _record_job(
            job_id=job_id,
            name=job_name,
            command=redacted_command,
            command_redacted=command_redacted,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=130,
            status="failed",
            duration_s=elapsed,
            output_summary=stdout_summary.summary(),
            error_summary=stderr_summary.summary(),
        )
        return 130

    elapsed = time.monotonic() - start
    for thread in output_threads:
        thread.join(timeout=1.0)
    finished_at = utc_now_iso()
    if return_code == 0:
        _emit_job_event(
            "job_finished",
            f"{job_name} completed in {_format_duration(elapsed)}",
            warned=bridge_warned,
            exit_code=return_code,
            duration_s=round(elapsed, 3),
            **event_base,
        )
        status = "succeeded"
    else:
        _emit_job_event(
            "job_failed",
            f"{job_name} failed with exit code {return_code} after {_format_duration(elapsed)}",
            warned=bridge_warned,
            exit_code=return_code,
            duration_s=round(elapsed, 3),
            **event_base,
        )
        status = "failed"

    _record_job(
        job_id=job_id,
        name=job_name,
        command=redacted_command,
        command_redacted=command_redacted,
        started_at=started_at,
        finished_at=finished_at,
        exit_code=int(return_code),
        status=status,
        duration_s=elapsed,
        output_summary=stdout_summary.summary(),
        error_summary=stderr_summary.summary(),
    )

    return int(return_code)


def _cmd_wrap(args: argparse.Namespace) -> int:
    command = _clean_command_remainder(list(args.command or []))
    if not command:
        command = _raw_command_after_separator(args)
    return _run_wrapped_command(
        command,
        name=str(getattr(args, "name", "") or ""),
        status_interval=max(0.0, float(getattr(args, "status_interval", 60.0) or 0.0)),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes-pet",
        description="Hermes Pet — a persistent CLI companion.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    status = subparsers.add_parser("status", help="Show full status and stats.")
    status.set_defaults(func=_cmd_status)

    hatch = subparsers.add_parser("hatch", help="Gacha a new pet (re-roll).")
    hatch.set_defaults(func=_cmd_hatch)

    rename = subparsers.add_parser("rename", help="Rename the current pet.")
    rename.add_argument("name", nargs="+", help="New pet name.")
    rename.set_defaults(func=_cmd_rename)

    feed = subparsers.add_parser("feed", help="Feed the pet for XP.")
    feed.set_defaults(func=_cmd_feed)

    pet = subparsers.add_parser("pet", help="Pet the pet for XP.")
    pet.set_defaults(func=_cmd_pet)

    play = subparsers.add_parser("play", help="Play with the pet for XP.")
    play.set_defaults(func=_cmd_play)

    species = subparsers.add_parser("species", help="List all species metadata.")
    species.set_defaults(func=_cmd_species)

    delete = subparsers.add_parser("delete", help="Release the current pet.")
    delete.set_defaults(func=_cmd_delete)

    launch = subparsers.add_parser("launch", help="Start the bridge and launch the overlay.")
    launch.add_argument(
        "--replace",
        action="store_true",
        help="Stop existing Hermes Pet overlay instances before launching a fresh one.",
    )
    launch.set_defaults(func=_launch_bridge_and_overlay)

    overlay_status = subparsers.add_parser("overlay-status", help="Show bridge and overlay process status.")
    overlay_status.set_defaults(func=_cmd_overlay_status)

    close = subparsers.add_parser("close", help="Stop Hermes Pet overlay processes.")
    close.add_argument(
        "--bridge",
        action="store_true",
        help="Also stop the Hermes Pet bridge process for the active port.",
    )
    close.set_defaults(func=_cmd_close)

    doctor = subparsers.add_parser("doctor", help="Run local Hermes Pet operator diagnostics.")
    doctor.set_defaults(func=_cmd_doctor)

    custom = subparsers.add_parser("custom", help="Set a custom PNG sprite.")
    custom.add_argument("path", help="Path to the PNG to copy into the pet state directory.")
    custom.set_defaults(func=_cmd_custom)

    emit = subparsers.add_parser("emit", help="Emit an ambient event to the live overlay.")
    emit.add_argument(
        "event_type",
        choices=sorted(EVENT_TYPES),
        help="Event type to emit.",
    )
    emit.add_argument("text", nargs="+", help="Human-facing event text.")
    emit.set_defaults(func=_cmd_emit)

    message = subparsers.add_parser("message", help="Emit an external message notification.")
    message.add_argument("--source", required=True, help="Message source, such as telegram or discord.")
    message.add_argument("--sender", required=True, help="Human-facing sender name.")
    message.add_argument(
        "--urgent",
        action="store_true",
        help="Mark the message as urgent and cut through overlay notification throttling.",
    )
    message.add_argument(
        "--open-command",
        default="",
        help="Local command or hint for how to open/respond; stored only, never executed by the overlay.",
    )
    message.add_argument("text", nargs="+", help="Message body to show, truncated before emitting.")
    message.set_defaults(func=_cmd_message)

    brief = subparsers.add_parser("brief", help="Summarize recent local Hermes Pet activity.")
    brief.add_argument(
        "--since",
        default="24h",
        help="Recent window to summarize, such as 30m, 2h, 24h, or 7d.",
    )
    brief.add_argument(
        "--emit",
        action="store_true",
        help="Send the summary to the overlay as a daily_brief event.",
    )
    brief.add_argument(
        "--telegram-text",
        action="store_true",
        help="Print a compact Telegram-friendly summary.",
    )
    brief.set_defaults(func=_cmd_brief)

    quiet = subparsers.add_parser("quiet", help="Adjust quiet mode for overlay bubbles.")
    quiet_group = quiet.add_mutually_exclusive_group()
    quiet_group.add_argument(
        "--silent",
        action="store_true",
        help="Suppress all non-critical bubbles.",
    )
    quiet_group.add_argument(
        "--off",
        action="store_true",
        help="Restore normal bubble behavior.",
    )
    quiet.set_defaults(func=_cmd_quiet)

    mute = subparsers.add_parser("mute", help="Mute non-urgent bubbles for a duration.")
    mute.add_argument("duration", help="Duration such as 30m, 2h, or 45s. Bare numbers mean minutes.")
    mute.set_defaults(func=_cmd_mute)

    prefs = subparsers.add_parser("prefs", help="Show or update notification preferences.")
    prefs_sub = prefs.add_subparsers(dest="prefs_action")
    prefs_set = prefs_sub.add_parser("set", help="Set one notification preference.")
    prefs_set.add_argument(
        "key",
        choices=[
            "muted_until",
            "quiet_mode",
            "bubble_throttle_seconds",
            "show_tray_on_urgent",
            "show_idle_bubbles",
        ],
        help="Preference key to update.",
    )
    prefs_set.add_argument("value", help="New preference value.")
    prefs.set_defaults(func=_cmd_prefs)
    prefs_set.set_defaults(func=_cmd_prefs, prefs_action="set")

    jobs = subparsers.add_parser("jobs", help="Show recent wrapped job history.")
    jobs.add_argument("--failed", action="store_true", help="Show only failed jobs.")
    jobs.add_argument("--last", action="store_true", help="Show detailed output for the latest matching job.")
    jobs.add_argument("--limit", type=int, default=20, help="Number of jobs to show.")
    jobs.set_defaults(func=_cmd_jobs)

    retry = subparsers.add_parser("retry", help="Rerun the latest failed wrapped command.")
    retry.add_argument(
        "--status-interval",
        type=float,
        default=60.0,
        help="Seconds between long-running status events; set 0 to disable.",
    )
    retry.set_defaults(func=_cmd_retry)

    run = subparsers.add_parser("run", help="Run a command and emit pet job lifecycle events.")
    run.add_argument("--name", "-n", default="", help="Optional job name shown in pet events.")
    run.add_argument(
        "--status-interval",
        type=float,
        default=60.0,
        help="Seconds between long-running status events; set 0 to disable.",
    )
    run.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --.")
    run.set_defaults(func=_cmd_wrap)

    wrap = subparsers.add_parser("wrap", help="Wrap a named command with pet job lifecycle events.")
    wrap.add_argument("--name", "-n", required=True, help="Job name shown in pet events.")
    wrap.add_argument(
        "--status-interval",
        type=float,
        default=60.0,
        help="Seconds between long-running status events; set 0 to disable.",
    )
    wrap.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --.")
    wrap.set_defaults(func=_cmd_wrap)

    parser.set_defaults(func=_cmd_bare)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(raw_argv)
    setattr(args, "_raw_argv", raw_argv)
    try:
        return int(args.func(args))
    except PetCLIError as exc:
        _print_error(str(exc))
        return 1
    except KeyboardInterrupt:
        _print_error("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
