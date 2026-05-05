"""
Hermes Pet Event Bridge
=======================
A tiny asyncio WebSocket server that can run inside the Hermes CLI process or
as a standalone bridge.

The Electron overlay connects to this bridge and receives real-time pet events
(tool completions, mood changes, XP, chat bubbles) as JSON messages.

Event types emitted by cli.py -> emit_pet_event():
  { "type": "mood_change", "mood": "idle"|"happy"|"thinking"|"busy" }
  { "type": "bubble",      "text": "Reading your code…", "duration": 3500 }
  { "type": "xp_change",   "delta": 10, "new_xp": 150, "new_level": 2 }
  { "type": "hatch",       "species": "duck", "name": "Quack", "variant": "shiny" }
  { "type": "state",       "species": ..., "name": ..., "level": ..., "xp": ..., "xp_next": ..., "variant": ..., "shiny": ... }
  { "type": "toggle_visible", "visible": true|false }

Usage inside Hermes CLI:
    from hermes_pet.bridge import PetEventBridge, emit_pet_event
    bridge = PetEventBridge()
    bridge.start()
    ...
    emit_pet_event({"type": "bubble", "text": "Found a bug!"})
"""

import asyncio
import json
import logging
import os
import signal
import socket
import time
from threading import Thread
from typing import Any, Optional

try:
    import websockets

    _WEBSOCKETS_AVAILABLE = True
except ImportError:
    _WEBSOCKETS_AVAILABLE = False

logger = logging.getLogger(__name__)

PET_BRIDGE_DEFAULT_PORT = 17473
PET_BRIDGE_DEFAULT_HOST = "127.0.0.1"


def _debug_events_enabled() -> bool:
    return os.getenv("HERMES_PET_DEBUG_EVENTS") == "1"


def _debug_event(message: str, *args: Any) -> None:
    if _debug_events_enabled():
        logger.info("[pet-bridge/events] " + message, *args)


def _resolve_port(port: Optional[int]) -> int:
    if port is not None:
        return port

    raw = os.getenv("HERMES_PET_PORT")
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning(
                "[pet-bridge] Invalid HERMES_PET_PORT=%r; using default %d",
                raw,
                PET_BRIDGE_DEFAULT_PORT,
            )
    return PET_BRIDGE_DEFAULT_PORT


def _resolve_host(host: Optional[str]) -> str:
    if host:
        return host
    return os.getenv("HERMES_PET_HOST") or PET_BRIDGE_DEFAULT_HOST


def _resolve_bridge_url(host: str, port: int, bridge_url: Optional[str]) -> str:
    return bridge_url or f"ws://{host}:{port}"


class PetEventBridge:
    """Async-based WebSocket fan-out server for pet overlay events.

    Designed to run in a background thread so it does not block the TUI event
    loop. Uses a thread-safe asyncio queue to receive events from the main
    thread (cli.py).
    """

    DEFAULT_PORT = PET_BRIDGE_DEFAULT_PORT
    DEFAULT_HOST = PET_BRIDGE_DEFAULT_HOST

    def __init__(
        self,
        port: Optional[int] = None,
        host: Optional[str] = None,
        bridge_url: Optional[str] = None,
    ):
        self.port = _resolve_port(port)
        self.host = _resolve_host(host)
        self.bridge_url = _resolve_bridge_url(self.host, self.port, bridge_url)
        self._clients: set[Any] = set()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._server: Optional[asyncio.AbstractServer] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the bridge in a background thread."""
        if self._running:
            return
        if not _WEBSOCKETS_AVAILABLE:
            logger.warning(
                "[pet-bridge] websockets package unavailable; overlay events disabled."
            )
            return

        self._running = True
        self._thread = Thread(target=self._run_bridge, daemon=True, name="PetEventBridge")
        self._thread.start()
        logger.info("[pet-bridge] Starting on %s", self.bridge_url)

    def stop(self) -> None:
        """Stop the background thread and close all clients."""
        if not self._running:
            return
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._queue.put_nowait, {"type": "__shutdown__"})
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None
        logger.info("[pet-bridge] Stopped")

    # ------------------------------------------------------------------
    # Async core (runs in background thread)
    # ------------------------------------------------------------------

    def _run_bridge(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main_loop())
        finally:
            self._loop.close()

    async def _main_loop(self) -> None:
        """Start the WebSocket server + event fan-out loop."""
        import websockets

        self._server = await websockets.serve(
            self._on_client_connected,
            host=self.host,
            port=self.port,
        )

        logger.info("[pet-bridge] Listening on %s", self.bridge_url)

        try:
            while self._running:
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue  # Normal — check running flag every 0.5s
                if event.get("type") == "__shutdown__":
                    break
                await self._broadcast(event)
        except Exception:
            pass  # Graceful — server will close below

        self._server.close()
        await self._server.wait_closed()

    # ------------------------------------------------------------------
    # Client connections
    # ------------------------------------------------------------------

    async def _on_client_connected(self, websocket) -> None:  # type: ignore[override]
        """Handle a new overlay client (Electron window)."""
        self._clients.add(websocket)
        logger.debug("[pet-bridge] Overlay connected (total %d)", len(self._clients))
        _debug_event("overlay connected clients=%d", len(self._clients))
        # Send current state immediately so overlay isn't blank.
        await self._maybe_send_state(websocket)
        await self._maybe_send_notification_prefs(websocket)
        await self._maybe_send_job_history(websocket)
        try:
            async for raw in websocket:
                try:
                    event = json.loads(raw)
                    if isinstance(event, dict):
                        _debug_event("received client event type=%s", event.get("type"))
                        await self._broadcast(event)
                except Exception:
                    logger.debug("[pet-bridge] Ignoring invalid client message")
        finally:
            self._clients.discard(websocket)
            logger.debug("[pet-bridge] Overlay disconnected (total %d)", len(self._clients))
            _debug_event("overlay disconnected clients=%d", len(self._clients))

    async def _broadcast(self, event: dict[str, Any]) -> None:
        """Fan-out one event to every connected client."""
        payload = json.dumps(event, separators=(",", ":"))
        dead = []
        _debug_event("broadcast type=%s clients=%d", event.get("type"), len(self._clients))
        for ws in list(self._clients):
            try:
                await ws.send(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    @staticmethod
    def _state_event(
        *,
        species: str,
        name: str,
        level: int,
        xp: int,
        variant: str,
        hat: str,
        favorite_tool: str = "",
    ) -> dict[str, Any]:
        return {
            "type": "state",
            "species": species,
            "name": name,
            "level": level,
            "xp": xp,
            "xp_next": level * 50,
            "variant": variant,
            "shiny": variant == "shiny",
            "hat": hat,
            "favorite_tool": favorite_tool,
        }

    async def _maybe_send_state(self, websocket) -> None:
        """Push current pet state to a newly-connected overlay.

        Respects ``HERMES_PET_SPECIES``: when the env var is set to a
        known species name, the overlay receives that species on connect,
        regardless of the persisted pet.
        """
        try:
            from hermes_pet.engine import SPECIES, load_pet

            override_species = (os.getenv("HERMES_PET_SPECIES") or "").strip().lower()
            if override_species and override_species not in SPECIES:
                logger.debug(
                    "[pet-bridge] HERMES_PET_SPECIES=%r is not a known species; ignoring",
                    override_species,
                )
                override_species = ""

            pet = load_pet("")  # no profile filtering for now

            if pet and (not override_species or pet.species == override_species):
                event = self._state_event(
                    species=getattr(pet, "species", ""),
                    name=getattr(pet, "name", ""),
                    level=int(getattr(pet, "level", 1)),
                    xp=int(getattr(pet, "xp", 0)),
                    variant=str(getattr(pet, "variant", "normal")),
                    hat=str(getattr(pet, "hat", "none")),
                    favorite_tool=getattr(SPECIES.get(getattr(pet, "species", "")), "favorite_tool", "")
                    or "",
                )
                _debug_event(
                    "send initial state type=%s species=%s",
                    event.get("type"),
                    event.get("species"),
                )
                await websocket.send(json.dumps(event, separators=(",", ":")))
                return

            if override_species:
                _debug_event(
                    "send synthesized initial state for HERMES_PET_SPECIES=%s (persisted=%s)",
                    override_species,
                    getattr(pet, "species", "none") if pet else "none",
                )
                species_def = SPECIES.get(override_species)
                await websocket.send(
                    json.dumps(
                        self._state_event(
                            species=override_species,
                            name="",
                            level=1,
                            xp=0,
                            variant="normal",
                            hat="none",
                            favorite_tool=getattr(species_def, "favorite_tool", "") or "",
                        ),
                        separators=(",", ":"),
                    )
                )
        except Exception:
            pass

    async def _maybe_send_job_history(self, websocket) -> None:
        """Seed the tray with a small persisted job history snapshot."""
        try:
            from hermes_pet.jobs import recent_jobs, utc_now_iso

            jobs = recent_jobs(limit=4, newest_first=True)
            if not jobs:
                return
            compact_jobs = []
            for job in jobs:
                compact_jobs.append(
                    {
                        "id": job.get("id"),
                        "name": job.get("name"),
                        "status": job.get("status"),
                        "exit_code": job.get("exit_code"),
                        "duration": job.get("duration"),
                        "duration_text": job.get("duration_text"),
                        "started_at": job.get("started_at"),
                        "finished_at": job.get("finished_at"),
                    }
                )
            await websocket.send(
                json.dumps(
                    {
                        "type": "job_history",
                        "text": "Recent jobs",
                        "severity": "info",
                        "created_at": utc_now_iso(),
                        "jobs": compact_jobs,
                    },
                    separators=(",", ":"),
                )
            )
        except Exception:
            pass

    async def _maybe_send_notification_prefs(self, websocket) -> None:
        """Send current notification policy to a newly-connected overlay."""
        try:
            from hermes_pet.prefs import load_prefs

            await websocket.send(
                json.dumps(
                    {
                        "type": "notification_prefs",
                        "prefs": load_prefs(),
                    },
                    separators=(",", ":"),
                )
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Thread-safe enqueue from cli.py
    # ------------------------------------------------------------------

    def emit(self, event: dict[str, Any]) -> None:
        """Called from the main thread to push an event into the queue."""
        if not self._running or self._loop is None:
            _debug_event(
                "drop local event type=%s running=%s loop=%s",
                event.get("type"),
                self._running,
                self._loop is not None,
            )
            return
        try:
            _debug_event("enqueue local event type=%s", event.get("type"))
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        except Exception:
            pass


# ------------------------------------------------------------------
# Shared singleton bridge instance managed by CLI or standalone helpers
# ------------------------------------------------------------------

_bridge_instance: Optional[PetEventBridge] = None


# ------------------------------------------------------------------
# Module-level helpers used by cli.py and gateway integrations
# ------------------------------------------------------------------

def start_bridge(
    port: Optional[int] = None,
    host: Optional[str] = None,
    bridge_url: Optional[str] = None,
) -> PetEventBridge:
    """Create, store, and start the global bridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = PetEventBridge(port=port, host=host, bridge_url=bridge_url)
        _bridge_instance.start()
    return _bridge_instance


def is_bridge_available(
    port: Optional[int] = None,
    host: Optional[str] = None,
    timeout: float = 0.25,
) -> bool:
    """Return True when a pet bridge TCP listener is already reachable."""
    resolved_port = _resolve_port(port)
    resolved_host = _resolve_host(host)
    try:
        with socket.create_connection((resolved_host, resolved_port), timeout=timeout):
            return True
    except OSError:
        return False


def send_event_to_bridge(
    event: dict[str, Any],
    port: Optional[int] = None,
    host: Optional[str] = None,
    bridge_url: Optional[str] = None,
) -> bool:
    """Send one event to an already-running external pet bridge."""
    if not _WEBSOCKETS_AVAILABLE:
        _debug_event(
            "cannot send external event type=%s websockets unavailable",
            event.get("type"),
        )
        return False

    resolved_port = _resolve_port(port)
    resolved_host = _resolve_host(host)
    url = _resolve_bridge_url(resolved_host, resolved_port, bridge_url)

    async def _send() -> None:
        import websockets

        async with websockets.connect(url, close_timeout=0.2) as ws:
            await ws.send(json.dumps(event, separators=(",", ":")))

    try:
        _debug_event("send external event type=%s url=%s", event.get("type"), url)
        asyncio.run(asyncio.wait_for(_send(), timeout=0.75))
        _debug_event("sent external event type=%s", event.get("type"))
        return True
    except Exception as exc:
        _debug_event("failed external event type=%s error=%s", event.get("type"), exc)
        return False


def stop_bridge() -> None:
    """Stop and clear the global bridge instance."""
    global _bridge_instance
    if _bridge_instance:
        _bridge_instance.stop()
        _bridge_instance = None


def emit_pet_event(event: dict[str, Any]) -> None:
    """Send an event to the currently-running bridge (thread-safe).

    Auto-starts the bridge on first emit so callers never need to worry
    about lifecycle.
    """
    global _bridge_instance
    if _bridge_instance is None:
        if is_bridge_available() and send_event_to_bridge(event):
            return
        try:
            _debug_event("auto-start bridge for event type=%s", event.get("type"))
            start_bridge()
        except Exception as exc:
            _debug_event(
                "failed to auto-start bridge for event type=%s error=%s",
                event.get("type"),
                exc,
            )
            return
    if _bridge_instance:
        _bridge_instance.emit(event)


def emit_message_received(source: str, sender: str | None = None) -> None:
    """Called by gateway platforms when an external message arrives.

    The overlay will show a chat bubble like "📱 New message from Telegram!"
    """
    emit_pet_event(
        {
            "type": "message_received",
            "source": source,
            "sender": sender or "someone",
        }
    )


def set_bridge_instance(inst: Optional[PetEventBridge]) -> None:
    """Override bridge — useful for testing or when HermesCLI manages its own."""
    global _bridge_instance
    _bridge_instance = inst


def serve_forever(
    port: Optional[int] = None,
    host: Optional[str] = None,
    bridge_url: Optional[str] = None,
) -> None:
    """Run the pet bridge as a small standalone process."""
    if not _WEBSOCKETS_AVAILABLE:
        logger.warning("[pet-bridge] websockets package unavailable; bridge cannot serve.")
        return

    bridge = start_bridge(port=port, host=host, bridge_url=bridge_url)
    stopping = False

    def _stop(_signum, _frame) -> None:
        nonlocal stopping
        stopping = True
        bridge.stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    try:
        while not stopping:
            time.sleep(0.5)
    finally:
        bridge.stop()


def main() -> None:
    import argparse

    if _debug_events_enabled():
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Run the Hermes pet event bridge.")
    parser.add_argument("--serve", action="store_true", help="Run the bridge until interrupted.")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bridge port. Overrides HERMES_PET_PORT for --serve and manual emits; default is 17473.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bridge host. Overrides HERMES_PET_HOST for --serve and manual emits; default is 127.0.0.1.",
    )
    parser.add_argument(
        "--bridge-url",
        default=None,
        help="Bridge WebSocket URL. Defaults to ws://<host>:<port>.",
    )
    parser.add_argument(
        "--emit-message-received",
        action="store_true",
        help="Emit a manual message_received test event to a running bridge.",
    )
    parser.add_argument("--source", default="test", help="Source for --emit-message-received (default: test).")
    parser.add_argument(
        "--sender",
        default="Manual test",
        help="Sender for --emit-message-received (default: Manual test).",
    )
    parser.add_argument("--emit-json", help="Emit a raw JSON event object to a running bridge.")
    args = parser.parse_args()
    emit_port = args.port
    emit_host = args.host
    emit_bridge_url = args.bridge_url

    if args.emit_json:
        try:
            event = json.loads(args.emit_json)
        except json.JSONDecodeError as exc:
            parser.error(f"--emit-json must be a JSON object: {exc}")
        if not isinstance(event, dict):
            parser.error("--emit-json must be a JSON object")
        if not send_event_to_bridge(event, port=emit_port, host=emit_host, bridge_url=emit_bridge_url):
            resolved_port = _resolve_port(emit_port)
            resolved_host = _resolve_host(emit_host)
            raise SystemExit(
                f"Failed to send pet event to {resolved_host}:{resolved_port}; is the bridge running?"
            )
        return

    if args.emit_message_received:
        event = {
            "type": "message_received",
            "source": args.source,
            "sender": args.sender,
        }
        if not send_event_to_bridge(event, port=emit_port, host=emit_host, bridge_url=emit_bridge_url):
            resolved_port = _resolve_port(emit_port)
            resolved_host = _resolve_host(emit_host)
            raise SystemExit(
                f"Failed to send message_received event to {resolved_host}:{resolved_port}; is the bridge running?"
            )
        return

    if args.serve:
        serve_forever(port=args.port, host=args.host, bridge_url=args.bridge_url)


if __name__ == "__main__":
    main()
