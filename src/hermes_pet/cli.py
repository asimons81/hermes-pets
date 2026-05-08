"""Standalone argparse CLI for Hermes Pets.

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
import json
from importlib import resources
from importlib.resources.abc import Traversable
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
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from hermes_pet.achievements import sync_achievements, unlock_achievement
from hermes_pet.custom_pets import (
    current_custom_pet,
    custom_pet_event_payload,
    custom_pet_preview_summary,
    custom_pets_dir,
    import_package,
    inspect_package,
    list_custom_pets,
    remove_custom_pet,
    render_custom_pet_preview_html,
    set_current_custom_pet,
    validate_pet_name,
)
from hermes_pet.voice import (
    load_voice_prefs,
    run_voice_for_event,
    run_voice_test,
    save_voice_prefs,
    set_voice_command,
    set_voice_enabled,
    voice_status,
)
from hermes_pet.engine import (
    Pet,
    delete_pet,
    gacha_rarity_table,
    get_all_species_info,
    load_pet,
    save_pet,
)
from hermes_pet.event_log import append_event, compact_events, load_events, safe_event
from hermes_pet.events import EVENT_TYPES, PetEventError, build_event
from hermes_pet.jobs import (
    HISTORY_LIMIT,
    OUTPUT_SUMMARY_LIMIT,
    append_job,
    compact_jobs,
    job_scan_summary,
    jobs_path,
    latest_failed_job,
    new_job_id,
    recent_jobs,
    redact_command,
    redact_text,
    utc_now_iso,
)
from hermes_pet.prefs import (
    NOTIFICATION_PROFILE_DEFAULTS,
    NOTIFICATION_PROFILES,
    QUIET_MODES,
    apply_notification_profile,
    load_prefs,
    mute_for,
    prefs_path,
    save_prefs,
    set_quiet_mode,
)

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


def _cache_dir() -> Path:
    return _state_dir() / "cache"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _source_overlay_dir() -> Path:
    return _repo_root() / "overlay"


def _overlay_required_files() -> tuple[str, ...]:
    return (
        "package.json",
        "src/main.js",
        "src/main.windows.js",
        "src/preload.js",
        "src/renderer.html",
        "src/renderer.js",
        "src/renderer.css",
        "assets/manifest.json",
        "scripts/launch-windows-overlay.ps1",
    )


def _is_overlay_runtime_dir(path: Path) -> bool:
    return path.is_dir() and all((path / rel).is_file() for rel in _overlay_required_files())


def _copy_overlay_resource_tree(source: Traversable, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        child_target = target / child.name
        if child.is_dir():
            _copy_overlay_resource_tree(child, child_target)
        elif child.is_file():
            child_target.parent.mkdir(parents=True, exist_ok=True)
            child_target.write_bytes(child.read_bytes())


def _packaged_overlay_resource() -> Traversable | None:
    try:
        overlay = resources.files("hermes_pet").joinpath("overlay")
    except (ModuleNotFoundError, AttributeError):
        return None
    if not overlay.is_dir():
        return None
    if not all(overlay.joinpath(*rel.split("/")).is_file() for rel in _overlay_required_files()):
        return None
    return overlay


def _ensure_cached_packaged_overlay() -> Path:
    overlay = _packaged_overlay_resource()
    if overlay is None:
        raise PetCLIError("Packaged overlay assets were not found. Reinstall Hermes Pets or use an editable repo install.")

    cache_overlay = _cache_dir() / "overlay"
    if cache_overlay.exists():
        shutil.rmtree(cache_overlay)
    _copy_overlay_resource_tree(overlay, cache_overlay)
    if not _is_overlay_runtime_dir(cache_overlay):
        raise PetCLIError(f"Cached overlay assets are incomplete: {cache_overlay}")
    return cache_overlay


def _overlay_dir() -> Path:
    source_overlay = _source_overlay_dir()
    if not os.environ.get("HERMES_PET_FORCE_PACKAGED_OVERLAY") and _is_overlay_runtime_dir(source_overlay):
        return source_overlay
    return _ensure_cached_packaged_overlay()


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
    _notify_achievement_unlocks(sync_achievements(_state_dir()))
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


def _cmd_doctor(args: argparse.Namespace) -> int:
    bridge_mod = importlib.import_module("hermes_pet.bridge")
    port = _resolve_bridge_port(bridge_mod)
    host = os.environ.get("HERMES_PET_HOST") or "127.0.0.1"
    state_dir = _state_dir()
    overlay_dir = _overlay_dir()
    checks: list[bool] = []

    print("Hermes Pets doctor")
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
            "available" if getattr(bridge_mod, "_WEBSOCKETS_AVAILABLE", False) else "missing; install Hermes Pets dependencies",
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
    if getattr(args, "strict", False):
        print("Strict mode: failing because one or more doctor checks warned.")
        return 1
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


def _notify_custom_pet_changed(payload: dict[str, object] | None) -> bool:
    bridge_mod = importlib.import_module("hermes_pet.bridge")
    port = _resolve_bridge_port(bridge_mod)
    host = os.environ.get("HERMES_PET_HOST") or "127.0.0.1"
    bridge_url = os.environ.get("HERMES_PET_WS_URL")
    return bridge_mod.send_event_to_bridge(
        {"type": "custom_pet", "custom_pet": payload},
        port=port,
        host=host,
        bridge_url=bridge_url,
    )


def _notify_achievement_unlocks(items: list[dict[str, object]]) -> None:
    if not items:
        return
    bridge_mod = importlib.import_module("hermes_pet.bridge")
    port = _resolve_bridge_port(bridge_mod)
    host = os.environ.get("HERMES_PET_HOST") or "127.0.0.1"
    bridge_url = os.environ.get("HERMES_PET_WS_URL")
    for item in items:
        bridge_mod.send_event_to_bridge(
            {"type": "achievement_unlocked", "achievement": item},
            port=port,
            host=host,
            bridge_url=bridge_url,
        )


def _unlock_and_notify_achievement(achievement_id: str, *, source: str) -> None:
    try:
        item = unlock_achievement(achievement_id, base_dir=_state_dir(), source=source)
    except Exception as exc:
        print(f"⚠️ Could not update achievements: {exc}", file=sys.stderr)
        return
    if item:
        _notify_achievement_unlocks([item])


def _cmd_custom_pet_list(_: argparse.Namespace) -> int:
    pets = list_custom_pets(_state_dir())
    if not pets:
        print(f"No custom pets installed in {_state_dir() / 'custom-pets'}.")
        return 0
    for pet in pets:
        marker = "*" if pet.get("current") else " "
        if pet.get("valid"):
            states = ", ".join(pet.get("states", []))
            print(f"{marker} {pet['name']}  ({states})")
        else:
            print(f"! {pet['name']}  invalid: {pet.get('error', 'unknown error')}")
    return 0


def _cmd_custom_pet_validate(args: argparse.Namespace) -> int:
    try:
        package = inspect_package(args.path, name=getattr(args, "name", None))
    except Exception as exc:
        raise PetCLIError(f"Custom pet validation failed: {exc}") from exc
    print(f"✅ Custom pet package is valid: {package.name}")
    print(f"Path:   {package.root}")
    print(f"Format: {package.source_format}")
    print(f"States: {', '.join(sorted(package.states))}")
    return 0


def _preview_output_path(package_name: str, output: str) -> Path:
    if output:
        path = Path(output).expanduser()
        if path.exists() and path.is_dir():
            return path / f"{package_name}-custom-pet-preview.html"
        if not path.suffix:
            return path / f"{package_name}-custom-pet-preview.html"
        return path
    return Path.cwd() / f"{package_name}-custom-pet-preview.html"


def _cmd_custom_pet_preview(args: argparse.Namespace) -> int:
    try:
        installed_name = str(getattr(args, "installed", "") or "").strip()
        path_arg = str(getattr(args, "path", "") or "").strip()
        if installed_name and path_arg:
            raise ValueError("choose either a package path or --installed, not both")
        if installed_name:
            name = validate_pet_name(installed_name)
            package = inspect_package(custom_pets_dir(_state_dir()) / name, name=name)
            source_label = f"installed custom pet {name}"
        elif path_arg:
            package = inspect_package(path_arg, name=getattr(args, "name", None))
            source_label = str(package.root)
        else:
            raise ValueError("provide a package path or --installed <name>")
    except Exception as exc:
        raise PetCLIError(f"Custom pet preview failed: {exc}") from exc

    output_path = _preview_output_path(package.name, str(getattr(args, "output", "") or ""))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_custom_pet_preview_html(package), encoding="utf-8")

    summary = custom_pet_preview_summary(package)
    print(f"Custom pet preview: {summary['name']}")
    print(f"Source: {source_label}")
    print(f"Format: {summary['source_format']}")
    print(f"HTML:   {output_path}")
    print()
    print("States")
    for state in summary["states"]:
        fallback = state["fallback"] or "none"
        loop = "loop" if state["loop"] else "one-shot"
        print(f"- {state['name']}: {state['frame_count']} frame(s), {state['fps']} fps, {loop}, fallback: {fallback}")
    missing = summary["missing_optional_states"]
    if missing:
        print()
        print(f"Missing optional states: {', '.join(missing)}")
        print("Missing optional states fall back to idle in the overlay.")
    else:
        print()
        print("Missing optional states: none")

    if getattr(args, "open", False) and not getattr(args, "no_open", False):
        try:
            webbrowser.open(output_path.resolve().as_uri())
        except Exception as exc:
            print(f"⚠️ Could not open preview automatically: {exc}", file=sys.stderr)
    return 0


def _cmd_custom_pet_import(args: argparse.Namespace) -> int:
    try:
        name = validate_pet_name(args.name)
        dest = import_package(args.path, name=name, base_dir=_state_dir())
    except Exception as exc:
        raise PetCLIError(f"Custom pet import failed: {exc}") from exc
    _unlock_and_notify_achievement("first_custom_pet_imported", source="custom-pet-import")
    print(f"✅ Imported custom pet {name} to {dest}")
    return 0


def _cmd_custom_pet_use(args: argparse.Namespace) -> int:
    try:
        payload = set_current_custom_pet(args.name, _state_dir())
    except Exception as exc:
        raise PetCLIError(f"Could not select custom pet: {exc}") from exc
    _notify_custom_pet_changed(payload)
    _unlock_and_notify_achievement("first_custom_pet_selected", source="custom-pet-use")
    print(f"✅ Using custom pet {payload['name']}")
    return 0


def _cmd_custom_pet_current(_: argparse.Namespace) -> int:
    payload = custom_pet_event_payload(_state_dir())
    if not payload:
        current = current_custom_pet(_state_dir())
        if current:
            print(f"Current custom pet is invalid or unavailable: {current.get('name')}")
        else:
            print("No custom pet selected.")
        return 0
    print(f"Current custom pet: {payload['name']}")
    print(f"Path: {payload['path']}")
    print(f"States: {', '.join(sorted(payload['manifest']['states']))}")
    return 0


def _cmd_custom_pet_remove(args: argparse.Namespace) -> int:
    try:
        name = validate_pet_name(args.name)
        remove_custom_pet(name, _state_dir())
    except Exception as exc:
        raise PetCLIError(f"Could not remove custom pet: {exc}") from exc
    _notify_custom_pet_changed(custom_pet_event_payload(_state_dir()))
    print(f"🗑️ Removed custom pet {name}")
    return 0


def _send_pet_event(event_type: str, text: str, *, required: bool, **extra: object) -> tuple[bool, dict[str, object]]:
    try:
        event = build_event(event_type, text, **extra)
    except PetEventError as exc:
        raise PetCLIError(str(exc)) from exc

    event = safe_event(event)
    try:
        append_event(event, base_dir=_state_dir())
    except Exception as exc:
        print(f"⚠️ Could not save event history: {exc}", file=sys.stderr)

    bridge_mod = importlib.import_module("hermes_pet.bridge")
    port = _resolve_bridge_port(bridge_mod)
    host = os.environ.get("HERMES_PET_HOST") or "127.0.0.1"
    bridge_url = os.environ.get("HERMES_PET_WS_URL")

    try:
        voice_result = run_voice_for_event(event, base_dir=_state_dir())
        if not voice_result.get("ok") and not voice_result.get("skipped"):
            print(f"⚠️ Voice preview failed: {voice_result.get('reason')}", file=sys.stderr)
    except Exception:
        print("⚠️ Voice preview failed: unexpected-error", file=sys.stderr)

    if not bridge_mod.send_event_to_bridge(event, port=port, host=host, bridge_url=bridge_url):
        if required:
            raise PetCLIError(
                f"Could not send event to ws://{host}:{port}. Run 'hermes-pet launch' first."
            )
        return False, event

    return True, event


def _clean_context_value(value: object) -> str:
    return _single_line(str(value or "")).strip()


def _git_project_defaults() -> dict[str, object]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(Path.cwd()),
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return {}
    if result.returncode != 0:
        return {}
    root = _clean_context_value(result.stdout)
    if not root:
        return {}
    path = Path(root).expanduser()
    return {
        "project_id": path.name,
        "project_path": str(path),
    }


def _event_context_from_args(args: argparse.Namespace, *, infer_project: bool = False) -> dict[str, object]:
    context: dict[str, object] = {}
    env_map = {
        "project_id": "HERMES_PET_PROJECT_ID",
        "project_path": "HERMES_PET_PROJECT_PATH",
        "session_id": "HERMES_PET_SESSION_ID",
        "session_label": "HERMES_PET_SESSION_LABEL",
    }
    for key, env_key in env_map.items():
        cli_value = _clean_context_value(getattr(args, key, ""))
        env_value = _clean_context_value(os.environ.get(env_key, ""))
        value = cli_value or env_value
        if value:
            context[key] = value

    if infer_project and not context.get("project_id") and not context.get("project_path"):
        context.update(_git_project_defaults())
    return context


def _cmd_emit(args: argparse.Namespace) -> int:
    event_type = str(args.event_type or "").strip().lower().replace("-", "_")
    text = " ".join(args.text).strip()
    _, event = _send_pet_event(event_type, text, required=True, **_event_context_from_args(args))

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
        extra["action_command"] = open_command

    extra.update(_event_context_from_args(args))

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
    print(f"notification_profile:   {_format_pref_value(prefs.get('notification_profile'))}")
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
    _unlock_and_notify_achievement("prefs_saved", source="prefs-quiet")
    if prefs.get("quiet_mode") in {"important", "silent"}:
        _unlock_and_notify_achievement("quiet_mode_enabled", source="prefs-quiet")
    print(f"🔕 Quiet mode: {prefs['quiet_mode']}")
    return 0


def _cmd_mute(args: argparse.Namespace) -> int:
    try:
        prefs = mute_for(_parse_duration(args.duration), _state_dir())
    except ValueError as exc:
        raise PetCLIError(str(exc)) from exc
    _notify_prefs_changed(prefs)
    _unlock_and_notify_achievement("prefs_saved", source="prefs-mute")
    print(f"🔇 Muted non-urgent bubbles until {prefs['muted_until']}")
    return 0


def _print_profiles() -> None:
    print("Notification profiles")
    for name in sorted(NOTIFICATION_PROFILES):
        defaults = NOTIFICATION_PROFILE_DEFAULTS[name]
        print(
            f"{name:8} quiet={defaults['quiet_mode']} "
            f"throttle={defaults['bubble_throttle_seconds']}s "
            f"tray={'on' if defaults['show_tray_on_urgent'] else 'off'} "
            f"idle={'on' if defaults['show_idle_bubbles'] else 'off'}"
        )


def _cmd_profile(args: argparse.Namespace) -> int:
    if getattr(args, "list", False):
        _print_profiles()
        return 0
    profile = str(getattr(args, "profile", "") or "").strip().lower()
    if not profile:
        _print_prefs(load_prefs(_state_dir()))
        return 0
    try:
        prefs = apply_notification_profile(profile, _state_dir())
    except ValueError as exc:
        raise PetCLIError(str(exc)) from exc
    _notify_prefs_changed(prefs)
    _unlock_and_notify_achievement("prefs_saved", source="prefs-profile")
    if prefs.get("quiet_mode") in {"important", "silent"}:
        _unlock_and_notify_achievement("quiet_mode_enabled", source="prefs-profile")
    print(f"✅ Notification profile: {prefs['notification_profile']}")
    return 0


def _coerce_pref_value(key: str, value: str) -> object:
    if key == "notification_profile":
        profile = value.strip().lower().replace("-", "_")
        if profile not in NOTIFICATION_PROFILES:
            raise PetCLIError(f"notification_profile must be one of: {', '.join(sorted(NOTIFICATION_PROFILES))}")
        return profile
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
    if getattr(args, "prefs_action", None) == "profile":
        setattr(args, "profile", args.profile)
        return _cmd_profile(args)

    if getattr(args, "prefs_action", None) == "set":
        if str(args.key).strip() == "notification_profile":
            setattr(args, "profile", args.value)
            return _cmd_profile(args)
        prefs = load_prefs(_state_dir())
        key = str(args.key).strip()
        prefs[key] = _coerce_pref_value(key, str(args.value))
        prefs = save_prefs(prefs, _state_dir())
        _notify_prefs_changed(prefs)
        _unlock_and_notify_achievement("prefs_saved", source="prefs-set")
        if prefs.get("quiet_mode") in {"important", "silent"}:
            _unlock_and_notify_achievement("quiet_mode_enabled", source="prefs-set")
        print(f"✅ Set {key}={_format_pref_value(prefs.get(key))}")
        return 0

    _print_prefs(load_prefs(_state_dir()))
    return 0


def _print_voice_status(payload: dict[str, object]) -> None:
    allowlist = payload.get("allowlist", [])
    allowlist_text = ", ".join(str(item) for item in allowlist) if isinstance(allowlist, list) else str(allowlist)
    print("Voice preview")
    print(f"enabled:        {_format_pref_value(payload.get('enabled'))}")
    print(f"command:        {_format_pref_value(payload.get('command'))}")
    print(f"command_source: {_format_pref_value(payload.get('command_source'))}")
    print(f"allowlist:      {allowlist_text}")


def _cmd_voice(args: argparse.Namespace) -> int:
    action = str(getattr(args, "voice_action", "") or "status")
    if action == "on":
        prefs = set_voice_enabled(True, _state_dir())
        _unlock_and_notify_achievement("voice_preview_enabled", source="voice-on")
        print("Voice preview enabled.")
        _print_voice_status({**voice_status(_state_dir()), **prefs})
        return 0
    if action == "off":
        prefs = set_voice_enabled(False, _state_dir())
        print("Voice preview disabled.")
        _print_voice_status({**voice_status(_state_dir()), **prefs})
        return 0
    if action == "set-command":
        prefs = set_voice_command(" ".join(getattr(args, "command", []) or []), _state_dir())
        print("Voice adapter command saved.")
        _print_voice_status({**voice_status(_state_dir()), **prefs})
        return 0
    if action == "test":
        text = " ".join(getattr(args, "text", []) or []) or "Hermes Pets voice preview test."
        result = run_voice_test(text, _state_dir())
        _unlock_and_notify_achievement("voice_test_ran", source="voice-test")
        print("Voice test result: " + ("ok" if result.get("ok") else "failed"))
        if result.get("reason"):
            print(f"reason: {result['reason']}")
        return 0 if result.get("ok") else 1
    _print_voice_status(voice_status(_state_dir()))
    return 0


def _cmd_dashboard(args: argparse.Namespace) -> int:
    from hermes_pet.dashboard import DashboardError, serve_dashboard

    requested_port = getattr(args, "port", 17474)
    port = 17474 if requested_port is None else int(requested_port)
    try:
        return serve_dashboard(
            host=str(getattr(args, "host", "127.0.0.1") or "127.0.0.1"),
            port=port,
            no_open=bool(getattr(args, "no_open", False)),
        )
    except DashboardError as exc:
        raise PetCLIError(str(exc)) from exc


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
        return

    if status == "succeeded" or int(exit_code) == 0:
        _unlock_and_notify_achievement("first_wrapped_job_completed", source="job-history")
    else:
        _unlock_and_notify_achievement("first_failed_job_recorded", source="job-history")
        if not command_redacted:
            _unlock_and_notify_achievement("first_retryable_failure", source="job-history")


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

    summary = job_scan_summary(jobs)
    print(
        "Jobs: "
        f"{summary['total']} shown, "
        f"{summary['succeeded']} succeeded, "
        f"{summary['failed']} failed, "
        f"{summary['retryable_failures']} retryable failure(s)"
    )
    print()
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
        line = f"{source} from {sender}: {text}" if text else f"{source} from {sender}"
    else:
        line = text or event_type
    hint = _event_action_hint(event, limit=max(24, limit // 2))
    if hint:
        line = f"{line} | Hint: {hint}"
    return _truncate_text(line, limit)


def _event_action_hint(event: dict[str, object], *, limit: int = 70) -> str:
    parts = []
    for key in ("action_label", "action_command", "action_url"):
        value = _single_line(str(event.get(key) or ""))
        if value:
            parts.append(value)
    if not parts:
        return ""
    return _truncate_text(" | ".join(parts), limit)


def _event_context_label(event: dict[str, object]) -> str:
    project = str(event.get("project_id") or "").strip()
    if not project:
        project_path = str(event.get("project_path") or "").strip()
        project = Path(project_path).name if project_path else ""
    session = str(event.get("session_label") or event.get("session_id") or "").strip()
    if project and session:
        return f"{project} / {session}"
    return project or session


def _event_is_urgent(event: dict[str, object]) -> bool:
    return (
        event.get("urgent") is True
        or str(event.get("urgency") or "").lower() == "urgent"
        or (event.get("type") == "message_received" and event.get("severity") == "warning")
    )


def _event_priority(event: dict[str, object]) -> tuple[int, int, int]:
    event_type = str(event.get("type") or "")
    if _event_is_urgent(event):
        rank = 0
    elif event_type == "approval_needed":
        rank = 1
    elif event_type == "job_failed":
        rank = 2
    elif event_type == "message_received":
        rank = 3
    elif _event_action_hint(event):
        rank = 4
    else:
        rank = 9
    event_time = _item_time(event)
    seconds = event_time.hour * 3600 + event_time.minute * 60 + event_time.second
    return rank, -event_time.toordinal(), -seconds


def _grouped_event_lines(events: list[dict[str, object]]) -> list[str]:
    groups: dict[str, list[dict[str, object]]] = {}
    for event in events:
        label = _event_context_label(event)
        if label:
            groups.setdefault(label, []).append(event)
    grouped_count = sum(len(items) for items in groups.values())
    if grouped_count < 2 and len(groups) < 2:
        return []

    lines: list[str] = []
    for label, items in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))[:4]:
        sorted_items = sorted(items, key=_event_priority)
        preview = "; ".join(_event_line(event, limit=72) for event in sorted_items[:2])
        lines.append(f"{label}: {len(items)} event(s)" + (f" - {preview}" if preview else ""))
    return lines


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
    prioritized_events = sorted(events, key=_event_priority)
    urgent_events = [event for event in prioritized_events if _event_is_urgent(event)]
    actionable_events = [event for event in prioritized_events if event.get("type") == "approval_needed" or _event_action_hint(event)]

    latest_status = "No recent activity found."
    if status_events:
        latest_status = _event_line(status_events[0])
    elif jobs:
        latest_status = f"Latest job {jobs[0].get('status', 'finished')}: {_job_line(jobs[0])}"
    elif messages:
        latest_status = f"Latest message: {_event_line(messages[0])}"

    if urgent_events:
        next_action = f"Handle urgent local event: {_event_line(urgent_events[0], limit=70)}"
    elif pending:
        next_action = f"Review approval needed: {_event_line(pending[0], limit=70)}"
    elif failures:
        next_action = f"Retry or inspect latest failure: {_job_line(failures[0], limit=70)}"
    elif actionable_events:
        next_action = f"Use stored action hint: {_event_line(actionable_events[0], limit=70)}"
    elif messages:
        next_action = f"Reply to latest message: {_event_line(messages[0], limit=70)}"
    elif successes:
        next_action = "No action needed; recent wrapped work is green."
    else:
        next_action = "Run work through hermes-pet wrap to build useful history."

    grouped_lines = _grouped_event_lines(events)

    if telegram_text:
        parts = [
            f"Hermes brief ({_format_duration(since.total_seconds())})",
            f"Status: {latest_status}",
            f"Urgent: {len(urgent_events)}",
            f"Failures: {len(failures)}",
            f"Successes: {len(successes)}",
            f"Pending: {len(pending)}",
        ]
        if messages:
            parts.append(f"Msg: {_event_line(messages[0], limit=70)}")
        if grouped_lines:
            parts.append(f"Group: {_truncate_text(grouped_lines[0], 82)}")
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
    lines.append("Top local events: " + ("none" if not prioritized_events else "; ".join(_event_line(event) for event in prioritized_events[:5])))
    if grouped_lines:
        lines.append("By project/session:")
        lines.extend(f"- {line}" for line in grouped_lines)
    lines.append(f"Suggested next action: {next_action}")
    return "\n".join(lines)


def _cmd_brief(args: argparse.Namespace) -> int:
    since = _parse_since_duration(str(getattr(args, "since", "24h") or "24h"))
    telegram_text = bool(getattr(args, "telegram_text", False))
    summary = _build_brief(since=since, telegram_text=telegram_text)
    if getattr(args, "emit", False):
        ok, event = _send_pet_event("daily_brief", summary, required=False, **_event_context_from_args(args))
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
        status=str(getattr(args, "status", "all") or "all"),
        query=str(getattr(args, "query", "") or ""),
        limit=max(1, int(getattr(args, "limit", 20) or 20)),
        newest_first=True,
    )
    if getattr(args, "last", False):
        _print_job_detail(jobs[0] if jobs else None)
        return 0

    _print_jobs_table(jobs)
    return 0


def _state_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None


def _build_state_export(args: argparse.Namespace) -> dict[str, object]:
    state_dir = _state_dir()
    since_arg = str(getattr(args, "since", "") or "").strip()
    cutoff = datetime.min.replace(tzinfo=timezone.utc)
    apply_cutoff = bool(since_arg)
    if since_arg:
        cutoff = datetime.now(timezone.utc) - _parse_since_duration(since_arg)

    jobs = [
        job
        for job in recent_jobs(base_dir=state_dir, limit=max(1, int(getattr(args, "limit", 100) or 100)), newest_first=True)
        if not apply_cutoff or _within_since(job, cutoff)
    ]
    events = [
        event
        for event in reversed(load_events(state_dir))
        if not apply_cutoff or _within_since(event, cutoff)
    ]
    pet_state = None if getattr(args, "no_pet", False) else _state_json(_pet_path())
    prefs = load_prefs(state_dir)
    return {
        "schema": "hermes.pet.export.v1",
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "state_dir": str(state_dir),
        "prefs": prefs,
        "pet": pet_state,
        "jobs": jobs,
        "events": events[: max(1, int(getattr(args, "event_limit", 100) or 100))],
        "summary": {
            "jobs": job_scan_summary(jobs),
            "events": len(events),
        },
    }


def _cmd_state_export(args: argparse.Namespace) -> int:
    payload = _build_state_export(args)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    output = str(getattr(args, "output", "") or "").strip()
    if output:
        path = Path(output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"✅ Exported Hermes Pets state to {path}")
        return 0
    print(text, end="")
    return 0


def _cmd_state_cleanup(args: argparse.Namespace) -> int:
    keep_jobs = max(0, int(getattr(args, "keep_jobs", HISTORY_LIMIT) or 0))
    keep_events = max(0, int(getattr(args, "keep_events", 200) or 0))
    dry_run = bool(getattr(args, "dry_run", False))
    current_jobs = recent_jobs(base_dir=_state_dir(), limit=HISTORY_LIMIT, newest_first=False)
    current_events = load_events(_state_dir())
    if dry_run:
        job_result = {"before": len(current_jobs), "after": min(len(current_jobs), keep_jobs), "removed": max(0, len(current_jobs) - keep_jobs)}
        event_result = {"before": len(current_events), "after": min(len(current_events), keep_events), "removed": max(0, len(current_events) - keep_events)}
    else:
        job_result = compact_jobs(base_dir=_state_dir(), keep=keep_jobs)
        event_result = compact_events(base_dir=_state_dir(), keep=keep_events)
    mode = "Would remove" if dry_run else "Removed"
    print(
        f"{mode} {job_result['removed']} job(s) and {event_result['removed']} event(s). "
        f"Kept {job_result['after']} job(s), {event_result['after']} event(s)."
    )
    return 0


def _cmd_state(_: argparse.Namespace) -> int:
    raise PetCLIError("Use 'hermes-pet state export' or 'hermes-pet state cleanup'.")


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
    return _run_wrapped_command_with_context(command, name=name, status_interval=status_interval, event_context={})


def _run_wrapped_command_with_context(
    command: list[str],
    *,
    name: str,
    status_interval: float,
    event_context: dict[str, object],
) -> int:
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
    event_base.update(event_context)

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
    return _run_wrapped_command_with_context(
        command,
        name=str(getattr(args, "name", "") or ""),
        status_interval=max(0.0, float(getattr(args, "status_interval", 60.0) or 0.0)),
        event_context=_event_context_from_args(args, infer_project=True),
    )


def _add_event_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", default="", help="Structured event project id. Defaults to HERMES_PET_PROJECT_ID.")
    parser.add_argument("--project-path", default="", help="Structured event project path. Defaults to HERMES_PET_PROJECT_PATH.")
    parser.add_argument("--session-id", default="", help="Structured event session id. Defaults to HERMES_PET_SESSION_ID.")
    parser.add_argument(
        "--session-label",
        default="",
        help="Human-facing event session label. Defaults to HERMES_PET_SESSION_LABEL.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes-pet",
        description="Hermes Pets — a persistent CLI companion.",
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
        help="Stop existing Hermes Pets overlay instances before launching a fresh one.",
    )
    launch.set_defaults(func=_launch_bridge_and_overlay)

    overlay_status = subparsers.add_parser("overlay-status", help="Show bridge and overlay process status.")
    overlay_status.set_defaults(func=_cmd_overlay_status)

    close = subparsers.add_parser("close", help="Stop Hermes Pets overlay processes.")
    close.add_argument(
        "--bridge",
        action="store_true",
        help="Also stop the Hermes Pets bridge process for the active port.",
    )
    close.set_defaults(func=_cmd_close)

    doctor = subparsers.add_parser("doctor", help="Run local Hermes Pets operator diagnostics.")
    doctor.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any doctor check reports a warning.",
    )
    doctor.set_defaults(func=_cmd_doctor)

    dashboard = subparsers.add_parser("dashboard", help="Serve the token-protected local dashboard.")
    dashboard.add_argument("--host", default="127.0.0.1", help="Local bind host. Must be localhost.")
    dashboard.add_argument("--port", type=int, default=17474, help="Local dashboard port.")
    dashboard.add_argument("--no-open", action="store_true", help="Print the dashboard URL without opening a browser.")
    dashboard.set_defaults(func=_cmd_dashboard)

    custom = subparsers.add_parser("custom", help="Set a custom PNG sprite.")
    custom.add_argument("path", help="Path to the PNG to copy into the pet state directory.")
    custom.set_defaults(func=_cmd_custom)

    custom_pet = subparsers.add_parser("custom-pet", help="Manage animated custom pets.")
    custom_pet_sub = custom_pet.add_subparsers(dest="custom_pet_action")

    custom_pet_list = custom_pet_sub.add_parser("list", help="List installed custom pets.")
    custom_pet_list.set_defaults(func=_cmd_custom_pet_list)

    custom_pet_validate = custom_pet_sub.add_parser("validate", help="Validate a custom pet package directory.")
    custom_pet_validate.add_argument("path", help="Package, hatch-pet run, or sprites folder to validate.")
    custom_pet_validate.add_argument("--name", default=None, help="Optional name to validate against.")
    custom_pet_validate.set_defaults(func=_cmd_custom_pet_validate)

    custom_pet_preview = custom_pet_sub.add_parser("preview", help="Generate an HTML animation preview for a custom pet.")
    custom_pet_preview.add_argument("path", nargs="?", help="Package, hatch-pet run, or sprites folder to preview.")
    custom_pet_preview.add_argument("--installed", default="", help="Preview an installed custom pet by name.")
    custom_pet_preview.add_argument("--name", default=None, help="Optional package name to validate candidate paths against.")
    custom_pet_preview.add_argument("--output", "-o", default="", help="Preview HTML file or output directory.")
    custom_pet_preview.add_argument("--open", action="store_true", help="Open the generated preview HTML in the default browser.")
    custom_pet_preview.add_argument("--no-open", action="store_true", help="Do not open the generated preview HTML.")
    custom_pet_preview.set_defaults(func=_cmd_custom_pet_preview)

    custom_pet_import = custom_pet_sub.add_parser("import", help="Import a custom pet package into local state.")
    custom_pet_import.add_argument("path", help="Package, hatch-pet run, or sprites folder to import.")
    custom_pet_import.add_argument("--name", required=True, help="Installed custom pet name.")
    custom_pet_import.set_defaults(func=_cmd_custom_pet_import)

    custom_pet_use = custom_pet_sub.add_parser("use", help="Select an installed custom pet for the overlay.")
    custom_pet_use.add_argument("name", help="Installed custom pet name.")
    custom_pet_use.set_defaults(func=_cmd_custom_pet_use)

    custom_pet_current = custom_pet_sub.add_parser("current", help="Show the selected custom pet.")
    custom_pet_current.set_defaults(func=_cmd_custom_pet_current)

    custom_pet_remove = custom_pet_sub.add_parser("remove", help="Remove an installed custom pet.")
    custom_pet_remove.add_argument("name", help="Installed custom pet name.")
    custom_pet_remove.set_defaults(func=_cmd_custom_pet_remove)
    custom_pet.set_defaults(func=_cmd_custom_pet_list)

    emit = subparsers.add_parser("emit", help="Emit an ambient event to the live overlay.")
    emit.add_argument(
        "event_type",
        choices=sorted(EVENT_TYPES),
        help="Event type to emit.",
    )
    emit.add_argument("text", nargs="+", help="Human-facing event text.")
    _add_event_context_args(emit)
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
    _add_event_context_args(message)
    message.add_argument("text", nargs="+", help="Message body to show, truncated before emitting.")
    message.set_defaults(func=_cmd_message)

    brief = subparsers.add_parser("brief", help="Summarize recent local Hermes Pets activity.")
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
    _add_event_context_args(brief)
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

    profile = subparsers.add_parser("profile", help="Use a named notification profile.")
    profile.add_argument(
        "profile",
        nargs="?",
        choices=sorted(NOTIFICATION_PROFILES),
        help="Profile to use: normal, focus, pairing, demo, or silent.",
    )
    profile.add_argument("--list", action="store_true", help="List available notification profiles.")
    profile.set_defaults(func=_cmd_profile)

    prefs = subparsers.add_parser("prefs", help="Show or update notification preferences.")
    prefs_sub = prefs.add_subparsers(dest="prefs_action")
    prefs_set = prefs_sub.add_parser("set", help="Set one notification preference.")
    prefs_set.add_argument(
        "key",
        choices=[
            "muted_until",
            "notification_profile",
            "quiet_mode",
            "bubble_throttle_seconds",
            "show_tray_on_urgent",
            "show_idle_bubbles",
        ],
        help="Preference key to update.",
    )
    prefs_set.add_argument("value", help="New preference value.")
    prefs_profile = prefs_sub.add_parser("profile", help="Use a named notification profile.")
    prefs_profile.add_argument("profile", nargs="?", choices=sorted(NOTIFICATION_PROFILES), help="Profile to apply.")
    prefs_profile.add_argument("--list", action="store_true", help="List available notification profiles.")
    prefs.set_defaults(func=_cmd_prefs)
    prefs_set.set_defaults(func=_cmd_prefs, prefs_action="set")
    prefs_profile.set_defaults(func=_cmd_prefs, prefs_action="profile")

    voice = subparsers.add_parser("voice", help="Manage opt-in voice preview mode.")
    voice_sub = voice.add_subparsers(dest="voice_action")
    voice_status_parser = voice_sub.add_parser("status", help="Show voice preview status.")
    voice_status_parser.set_defaults(func=_cmd_voice, voice_action="status")
    voice_on = voice_sub.add_parser("on", help="Enable voice preview.")
    voice_on.set_defaults(func=_cmd_voice, voice_action="on")
    voice_off = voice_sub.add_parser("off", help="Disable voice preview.")
    voice_off.set_defaults(func=_cmd_voice, voice_action="off")
    voice_command = voice_sub.add_parser("set-command", help="Save the adapter command used for voice preview.")
    voice_command.add_argument("command", nargs=argparse.REMAINDER, help="Command to run; event text is sent on stdin.")
    voice_command.set_defaults(func=_cmd_voice, voice_action="set-command")
    voice_test = voice_sub.add_parser("test", help="Run one explicit voice preview test.")
    voice_test.add_argument("text", nargs="*", help="Text to send to the adapter.")
    voice_test.set_defaults(func=_cmd_voice, voice_action="test")
    voice.set_defaults(func=_cmd_voice, voice_action="status")

    jobs = subparsers.add_parser("jobs", help="Show recent wrapped job history.")
    jobs.add_argument("--failed", action="store_true", help="Show only failed jobs.")
    jobs.add_argument(
        "--status",
        choices=["all", "succeeded", "failed"],
        default="all",
        help="Filter by job status.",
    )
    jobs.add_argument("--query", default="", help="Filter jobs by name, command, output, or error text.")
    jobs.add_argument("--last", action="store_true", help="Show detailed output for the latest matching job.")
    jobs.add_argument("--limit", type=int, default=20, help="Number of jobs to show.")
    jobs.set_defaults(func=_cmd_jobs)

    state = subparsers.add_parser("state", help="Export or compact local Hermes Pets state.")
    state_sub = state.add_subparsers(dest="state_action")
    state_export = state_sub.add_parser("export", help="Export compact local state as redacted JSON.")
    state_export.add_argument("--output", "-o", default="", help="Optional output JSON path. Defaults to stdout.")
    state_export.add_argument("--since", default="", help="Only include jobs/events in a recent window such as 24h or 7d.")
    state_export.add_argument("--limit", type=int, default=100, help="Maximum jobs to include.")
    state_export.add_argument("--event-limit", type=int, default=100, help="Maximum events to include.")
    state_export.add_argument("--no-pet", action="store_true", help="Omit pet.json from the export.")
    state_export.set_defaults(func=_cmd_state_export)
    state_cleanup = state_sub.add_parser("cleanup", help="Compact bounded local jobs and event history.")
    state_cleanup.add_argument("--keep-jobs", type=int, default=HISTORY_LIMIT, help="Number of recent jobs to keep.")
    state_cleanup.add_argument("--keep-events", type=int, default=200, help="Number of recent events to keep.")
    state_cleanup.add_argument("--dry-run", action="store_true", help="Print cleanup counts without writing.")
    state_cleanup.set_defaults(func=_cmd_state_cleanup)
    state.set_defaults(func=_cmd_state)

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
    _add_event_context_args(run)
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
    _add_event_context_args(wrap)
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
