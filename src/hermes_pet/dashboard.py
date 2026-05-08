"""Localhost-only dashboard server and API helpers."""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from hermes_pet.achievements import (
    achievement_status,
    sync_achievements,
    unlock_achievement,
)
from hermes_pet.custom_pets import (
    clear_current_custom_pet,
    custom_pet_event_payload,
    custom_pet_preview_summary,
    custom_pets_dir,
    import_package,
    inspect_package,
    list_custom_pets,
    remove_custom_pet,
    set_current_custom_pet,
    validate_pet_name,
)
from hermes_pet.engine import SPECIES, Pet, get_all_species_info, load_pet, save_pet
from hermes_pet.event_log import append_event, load_events, safe_event
from hermes_pet.events import build_event
from hermes_pet.jobs import job_scan_summary, recent_jobs
from hermes_pet.prefs import (
    NOTIFICATION_PROFILE_DEFAULTS,
    NOTIFICATION_PROFILES,
    QUIET_MODES,
    load_prefs,
    normalize_prefs,
    save_prefs,
)
from hermes_pet.voice import load_voice_prefs, run_voice_test, save_voice_prefs, voice_status


DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}
DASHBOARD_PORT = 17474
RESOURCE_ROOT = "dashboard"


class DashboardError(RuntimeError):
    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def state_dir() -> Path:
    return Path(os.environ.get("HERMES_PET_HOME") or "~/.hermes_pet").expanduser()


def dashboard_resource_root():
    try:
        root = resources.files("hermes_pet").joinpath(RESOURCE_ROOT)
    except (ModuleNotFoundError, AttributeError):
        return None
    if not root.is_dir() or not root.joinpath("index.html").is_file():
        return None
    return root


def require_dashboard_assets() -> Any:
    root = dashboard_resource_root()
    if root is None:
        raise DashboardError(
            "Dashboard assets were not found. Reinstall Hermes Pets or run from a complete editable checkout.",
            status=500,
        )
    return root


def _join_resource(root: Any, parts: tuple[str, ...]) -> Any:
    target = root
    for part in parts:
        target = target.joinpath(part)
    return target


def _bridge_status() -> dict[str, object]:
    try:
        from hermes_pet import bridge

        port = bridge._resolve_port(None)
        host = os.environ.get("HERMES_PET_HOST") or "127.0.0.1"
        available = bridge.is_bridge_available(port=port, host=host)
        return {"host": host, "port": port, "available": available}
    except Exception as exc:
        return {"host": "127.0.0.1", "port": 17473, "available": False, "error": str(exc)}


def _pet_snapshot(base_dir: Path) -> dict[str, object] | None:
    pet = load_pet("", state_dir=base_dir)
    if pet is None:
        return None
    payload = pet.to_dict()
    payload["xp_next"] = pet.level * 50
    return payload


def _recent_events(base_dir: Path, limit: int = 12) -> list[dict[str, Any]]:
    events = load_events(base_dir)
    return list(reversed(events[-limit:]))


def _recent_jobs(base_dir: Path, limit: int = 8) -> list[dict[str, Any]]:
    return recent_jobs(base_dir=base_dir, limit=limit, newest_first=True)


def build_state_snapshot(*, base_dir: Path | None = None, server: dict[str, object] | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    new_unlocks = sync_achievements(root)
    jobs = _recent_jobs(root)
    events = _recent_events(root)
    return {
        "schema": "hermes.pet.dashboard.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "state_dir": str(root),
        "server": server or {},
        "pet": _pet_snapshot(root),
        "custom_pet": custom_pet_event_payload(root),
        "custom_pets": list_custom_pets(root),
        "prefs": load_prefs(root),
        "voice": voice_status(root),
        "jobs": jobs,
        "job_summary": job_scan_summary(list(reversed(jobs))),
        "events": events,
        "achievements": achievement_status(root),
        "new_achievements": new_unlocks,
        "bridge": _bridge_status(),
    }


def _notify_bridge(event: dict[str, Any]) -> bool:
    try:
        from hermes_pet import bridge

        port = bridge._resolve_port(None)
        host = os.environ.get("HERMES_PET_HOST") or "127.0.0.1"
        bridge_url = os.environ.get("HERMES_PET_WS_URL")
        return bool(bridge.send_event_to_bridge(event, port=port, host=host, bridge_url=bridge_url))
    except Exception:
        return False


def emit_achievement_unlocks(items: list[dict[str, Any]]) -> None:
    for item in items:
        _notify_bridge({"type": "achievement_unlocked", "achievement": item})


def unlock_dashboard_achievement(root: Path, achievement_id: str, source: str) -> dict[str, Any] | None:
    item = unlock_achievement(achievement_id, base_dir=root, source=source)
    if item:
        emit_achievement_unlocks([item])
    return item


def get_dashboard_prefs(base_dir: Path | None = None) -> dict[str, object]:
    return {
        "prefs": load_prefs(base_dir or state_dir()),
        "profiles": {name: NOTIFICATION_PROFILE_DEFAULTS[name] for name in sorted(NOTIFICATION_PROFILES)},
        "quiet_modes": sorted(QUIET_MODES),
    }


def _pet_change_payload(root: Path, pet: Pet, *, action: str, custom_selection_cleared: bool) -> dict[str, object]:
    event = pet.to_event_dict()
    event["type"] = "hatch"
    event["action"] = action
    event["custom_pet"] = None
    pet_notified = _notify_bridge(event)
    custom_notified = _notify_bridge({"type": "custom_pet", "custom_pet": None})
    unlock_dashboard_achievement(root, "first_builtin_pet_change", f"dashboard-{action}")
    return {
        "action": action,
        "pet": _pet_snapshot(root),
        "custom_pet": custom_pet_event_payload(root),
        "custom_selection_cleared": custom_selection_cleared,
        "bridge_notified": pet_notified,
        "custom_bridge_notified": custom_notified,
        "snapshot": build_state_snapshot(base_dir=root),
    }


def list_dashboard_species_catalog(base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    species = sorted(get_all_species_info(), key=lambda item: str(item["name"]))
    return {"species": species, "current": _pet_snapshot(root)}


def hatch_dashboard_random_pet(base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    pet = Pet.hatch("", force_seed=secrets.randbits(64))
    save_pet(pet, state_dir=root)
    cleared = clear_current_custom_pet(root)
    return _pet_change_payload(root, pet, action="random_hatch", custom_selection_cleared=cleared)


def adopt_dashboard_species(data: dict[str, Any], base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    if not isinstance(data, dict):
        raise DashboardError("Expected a JSON object.")
    species = str(data.get("species") or "").strip().lower()
    if not species:
        raise DashboardError("Provide a species name.")
    if species not in SPECIES:
        raise DashboardError(f"Unknown species: {species}", status=404)
    try:
        pet = Pet.hatch("", force_seed=secrets.randbits(64), species=species)
    except Exception as exc:
        raise DashboardError(str(exc)) from exc
    save_pet(pet, state_dir=root)
    cleared = clear_current_custom_pet(root)
    return _pet_change_payload(root, pet, action="adopt_species", custom_selection_cleared=cleared)


def clear_dashboard_custom_pet(base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    cleared = clear_current_custom_pet(root)
    _notify_bridge({"type": "custom_pet", "custom_pet": None})
    if cleared:
        unlock_dashboard_achievement(root, "custom_pet_cleared", "dashboard-clear-custom")
    return {
        "cleared": cleared,
        "custom_pet": custom_pet_event_payload(root),
        **list_dashboard_custom_pets(root),
        "snapshot": build_state_snapshot(base_dir=root),
    }


def update_dashboard_prefs(data: dict[str, Any], base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    if not isinstance(data, dict):
        raise DashboardError("Expected a JSON object.")
    allowed = {
        "notification_profile",
        "quiet_mode",
        "bubble_throttle_seconds",
        "show_tray_on_urgent",
        "show_idle_bubbles",
        "muted_until",
    }
    current = load_prefs(root)
    updates = {key: data[key] for key in allowed if key in data}
    if "notification_profile" in updates:
        requested = str(updates["notification_profile"] or "").strip().lower().replace("-", "_")
        if requested not in NOTIFICATION_PROFILES:
            raise DashboardError("Unknown notification profile.")
        current.update(NOTIFICATION_PROFILE_DEFAULTS[requested])
        current["notification_profile"] = requested
    current.update(updates)
    normalized = normalize_prefs(current)
    saved = save_prefs(normalized, root)
    bridge_notified = _notify_bridge({"type": "notification_prefs", "prefs": saved})
    unlock_dashboard_achievement(root, "prefs_saved", "dashboard-prefs")
    if saved.get("quiet_mode") in {"important", "silent"}:
        unlock_dashboard_achievement(root, "quiet_mode_enabled", "dashboard-prefs")
    return {"prefs": saved, "bridge_notified": bridge_notified}


def list_dashboard_custom_pets(base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    pets = list_custom_pets(root)
    for pet in pets:
        if not pet.get("valid"):
            continue
        try:
            package = inspect_package(custom_pets_dir(root) / str(pet["name"]), name=str(pet["name"]))
            summary = custom_pet_preview_summary(package)
        except Exception as exc:
            pet["valid"] = False
            pet["error"] = str(exc)
            continue
        pet["state_summary"] = [
            {"name": item["name"], "frame_count": item["frame_count"], "fps": item["fps"]}
            for item in summary["states"]
        ]
        pet["missing_optional_states"] = summary["missing_optional_states"]
    current = custom_pet_event_payload(root)
    return {"pets": pets, "current": current, "directory": str(custom_pets_dir(root))}


def import_dashboard_custom_pet(data: dict[str, Any], base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    path = str(data.get("path") or "").strip() if isinstance(data, dict) else ""
    name = str(data.get("name") or "").strip() if isinstance(data, dict) else ""
    if not path or not name:
        raise DashboardError("Provide both path and installed name.")
    try:
        slug = validate_pet_name(name)
        dest = import_package(path, name=slug, base_dir=root)
    except Exception as exc:
        raise DashboardError(str(exc)) from exc
    unlocked = unlock_achievement("first_custom_pet_imported", base_dir=root, source="dashboard-import")
    if unlocked:
        emit_achievement_unlocks([unlocked])
    return {"imported": {"name": slug, "path": str(dest)}, **list_dashboard_custom_pets(root)}


def use_dashboard_custom_pet(data: dict[str, Any], base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    name = str(data.get("name") or "").strip() if isinstance(data, dict) else ""
    try:
        payload = set_current_custom_pet(name, root)
    except Exception as exc:
        raise DashboardError(str(exc)) from exc
    _notify_bridge({"type": "custom_pet", "custom_pet": payload})
    unlocked = unlock_achievement("first_custom_pet_selected", base_dir=root, source="dashboard-use")
    if unlocked:
        emit_achievement_unlocks([unlocked])
    return {"current": payload, **list_dashboard_custom_pets(root)}


def remove_dashboard_custom_pet(name: str, base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    try:
        remove_custom_pet(name, root)
    except Exception as exc:
        raise DashboardError(str(exc), status=404) from exc
    _notify_bridge({"type": "custom_pet", "custom_pet": custom_pet_event_payload(root)})
    return list_dashboard_custom_pets(root)


def preview_dashboard_custom_pet(name: str, base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    try:
        slug = validate_pet_name(name)
        package = inspect_package(custom_pets_dir(root) / slug, name=slug)
    except Exception as exc:
        raise DashboardError(str(exc), status=404) from exc
    return {"summary": custom_pet_preview_summary(package)}


def get_dashboard_voice(base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    return {"prefs": load_voice_prefs(root), "status": voice_status(root)}


def update_dashboard_voice(data: dict[str, Any], base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    if not isinstance(data, dict):
        raise DashboardError("Expected a JSON object.")
    prefs = load_voice_prefs(root)
    if "enabled" in data:
        prefs["enabled"] = bool(data["enabled"])
    if "command" in data:
        prefs["command"] = str(data["command"] or "").strip()
    if "timeout_seconds" in data:
        prefs["timeout_seconds"] = data["timeout_seconds"]
    saved = save_voice_prefs(prefs, root)
    if saved.get("enabled"):
        unlock_dashboard_achievement(root, "voice_preview_enabled", "dashboard-voice")
    return {"prefs": saved, "status": voice_status(root)}


def test_dashboard_voice(data: dict[str, Any], base_dir: Path | None = None) -> dict[str, object]:
    if not isinstance(data, dict):
        raise DashboardError("Expected a JSON object.")
    root = base_dir or state_dir()
    text = str((data or {}).get("text") or "Hermes Pets voice preview test.").strip()
    result = run_voice_test(text, root)
    unlock_dashboard_achievement(root, "voice_test_ran", "dashboard-voice-test")
    return {"result": result, **get_dashboard_voice(root)}


def emit_dashboard_test_event(base_dir: Path | None = None) -> dict[str, object]:
    root = base_dir or state_dir()
    event = safe_event(build_event("status", "Dashboard test event reached the overlay.", source="dashboard"))
    append_event(event, base_dir=root)
    unlock_dashboard_achievement(root, "first_test_event_sent", "dashboard-test-event")
    return {"event": event, "bridge_notified": _notify_bridge(event)}


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server_version = "HermesPetDashboard/0.3"

    def log_message(self, format: str, *args: object) -> None:
        if getattr(self.server, "quiet", False):
            return
        super().log_message(format, *args)

    @property
    def dashboard_server(self) -> "DashboardHTTPServer":
        return self.server  # type: ignore[return-value]

    def _token_from_cookie(self) -> str:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            key, _, value = part.strip().partition("=")
            if key == "hermes_pet_dashboard_token":
                return value
        return ""

    def _authorized(self) -> bool:
        parsed = urlparse(self.path)
        query_token = parse_qs(parsed.query).get("token", [""])[0]
        header_token = self.headers.get("X-Hermes-Pet-Token", "")
        return self.dashboard_server.token in {query_token, header_token, self._token_from_cookie()}

    def _send_json(self, payload: object, *, status: int = 200) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, *, status: int = 400) -> None:
        self._send_json({"error": message, "status": status}, status=status)

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._send_error_json("Dashboard token required.", status=401)
        return False

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 1024 * 1024))
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise DashboardError(f"Invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise DashboardError("Expected a JSON object.")
        return data

    def do_GET(self) -> None:
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/state":
                open_unlock = unlock_dashboard_achievement(
                    self.dashboard_server.state_dir,
                    "first_dashboard_opened",
                    "dashboard-open",
                )
                sync_unlocks = sync_achievements(self.dashboard_server.state_dir)
                emit_achievement_unlocks(sync_unlocks)
                self._send_json(build_state_snapshot(base_dir=self.dashboard_server.state_dir, server=self.dashboard_server.metadata()))
            elif parsed.path == "/api/species":
                self._send_json(list_dashboard_species_catalog(self.dashboard_server.state_dir))
            elif parsed.path == "/api/prefs":
                self._send_json(get_dashboard_prefs(self.dashboard_server.state_dir))
            elif parsed.path == "/api/custom-pets":
                self._send_json(list_dashboard_custom_pets(self.dashboard_server.state_dir))
            elif parsed.path.startswith("/api/custom-pets/") and parsed.path.endswith("/preview"):
                name = unquote(parsed.path.split("/")[-2])
                self._send_json(preview_dashboard_custom_pet(name, self.dashboard_server.state_dir))
            elif parsed.path == "/api/voice":
                self._send_json(get_dashboard_voice(self.dashboard_server.state_dir))
            elif parsed.path == "/api/achievements":
                sync_achievements(self.dashboard_server.state_dir)
                self._send_json(achievement_status(self.dashboard_server.state_dir))
            elif parsed.path.startswith("/api/"):
                self._send_error_json("Unknown API endpoint.", status=404)
            elif parsed.path.startswith("/overlay/assets/"):
                self._serve_overlay_asset(parsed.path)
            else:
                self._serve_static(parsed.path, parsed.query)
        except DashboardError as exc:
            self._send_error_json(str(exc), status=exc.status)
        except Exception as exc:
            self._send_error_json(str(exc), status=500)

    def do_POST(self) -> None:
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        try:
            data = self._read_json()
            if parsed.path == "/api/prefs":
                self._send_json(update_dashboard_prefs(data, self.dashboard_server.state_dir))
            elif parsed.path == "/api/pets/random-hatch":
                self._send_json(hatch_dashboard_random_pet(self.dashboard_server.state_dir), status=201)
            elif parsed.path == "/api/pets/adopt":
                self._send_json(adopt_dashboard_species(data, self.dashboard_server.state_dir), status=201)
            elif parsed.path == "/api/custom-pets/import":
                self._send_json(import_dashboard_custom_pet(data, self.dashboard_server.state_dir), status=201)
            elif parsed.path == "/api/custom-pets/use":
                self._send_json(use_dashboard_custom_pet(data, self.dashboard_server.state_dir))
            elif parsed.path == "/api/custom-pets/clear-current":
                self._send_json(clear_dashboard_custom_pet(self.dashboard_server.state_dir))
            elif parsed.path == "/api/events/test":
                self._send_json(emit_dashboard_test_event(self.dashboard_server.state_dir))
            elif parsed.path == "/api/voice":
                self._send_json(update_dashboard_voice(data, self.dashboard_server.state_dir))
            elif parsed.path == "/api/voice/test":
                self._send_json(test_dashboard_voice(data, self.dashboard_server.state_dir))
            else:
                self._send_error_json("Unknown API endpoint.", status=404)
        except DashboardError as exc:
            self._send_error_json(str(exc), status=exc.status)
        except Exception as exc:
            self._send_error_json(str(exc), status=500)

    def do_DELETE(self) -> None:
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/custom-pets/"):
                name = unquote(parsed.path.rsplit("/", 1)[-1])
                self._send_json(remove_dashboard_custom_pet(name, self.dashboard_server.state_dir))
            else:
                self._send_error_json("Unknown API endpoint.", status=404)
        except DashboardError as exc:
            self._send_error_json(str(exc), status=exc.status)
        except Exception as exc:
            self._send_error_json(str(exc), status=500)

    def _serve_static(self, path: str, query: str) -> None:
        if path in {"", "/"}:
            rel = "index.html"
        else:
            rel = path.lstrip("/")
        if "/" in rel:
            rel_path = Path(rel)
            if any(part in {"", ".", ".."} for part in rel_path.parts):
                self._send_error_json("Invalid dashboard asset path.", status=404)
                return
        root = require_dashboard_assets()
        target = _join_resource(root, Path(rel).parts)
        if not target.is_file():
            self._send_error_json("Dashboard asset not found.", status=404)
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(rel)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        token = parse_qs(query).get("token", [""])[0]
        if token == self.dashboard_server.token:
            self.send_header("Set-Cookie", f"hermes_pet_dashboard_token={token}; Path=/; SameSite=Strict")
        self.end_headers()
        self.wfile.write(body)

    def _serve_overlay_asset(self, path: str) -> None:
        rel = path.removeprefix("/overlay/assets/")
        rel_path = Path(rel)
        if any(part in {"", ".", ".."} for part in rel_path.parts):
            self._send_error_json("Invalid overlay asset path.", status=404)
            return
        try:
            root = resources.files("hermes_pet").joinpath("overlay").joinpath("assets")
        except (ModuleNotFoundError, AttributeError):
            self._send_error_json("Overlay assets unavailable.", status=404)
            return
        target = _join_resource(root, rel_path.parts)
        if not target.is_file():
            self._send_error_json("Overlay asset not found.", status=404)
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(rel)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class DashboardHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], token: str, state_dir: Path, quiet: bool = False) -> None:
        super().__init__(server_address, DashboardRequestHandler)
        self.token = token
        self.state_dir = state_dir
        self.quiet = quiet

    def metadata(self) -> dict[str, object]:
        host, port = self.server_address[:2]
        return {"host": host, "port": port, "localhost_only": True}


def dashboard_url(host: str, port: int, token: str) -> str:
    return f"http://{host}:{port}/?token={token}"


def serve_dashboard(host: str = "127.0.0.1", port: int = DASHBOARD_PORT, *, no_open: bool = False) -> int:
    host = str(host or "127.0.0.1").strip()
    if host not in DASHBOARD_HOSTS:
        raise DashboardError("Dashboard is localhost-only. Use 127.0.0.1, localhost, or ::1.", status=400)
    require_dashboard_assets()
    token = secrets.token_urlsafe(24)
    server = DashboardHTTPServer((host, int(port)), token, state_dir())
    resolved_host, resolved_port = server.server_address[:2]
    url = dashboard_url(resolved_host, resolved_port, token)
    print(f"Hermes Pets dashboard: {url}")
    print("Localhost-only; keep this token URL private. Press Ctrl+C to stop.")
    if not no_open:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
    return 0
