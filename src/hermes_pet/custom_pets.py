"""Custom animated pet package support for Hermes Pets."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from base64 import b64encode
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from hermes_pet.prefs import state_dir

PACKAGE_VERSION = 1
CURRENT_SELECTION_FILE = "custom-pet-current.json"
CUSTOM_PET_METADATA = "custom-pet.json"
SAFE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SAFE_FRAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.png$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

STATE_MAP = {
    "idle": ("idle", 4, True, None),
    "running-right": ("run_right", 9, True, None),
    "running-left": ("run_left", 9, True, None),
    "run-right": ("run_right", 9, True, None),
    "run-left": ("run_left", 9, True, None),
    "run_right": ("run_right", 9, True, None),
    "run_left": ("run_left", 9, True, None),
    "waving": ("waving", 8, False, "idle"),
    "jumping": ("jumping", 8, False, "idle"),
    "failed": ("failed", 7, False, "idle"),
    "waiting": ("waiting", 5, True, None),
    "running": ("running", 8, True, None),
    "review": ("review", 6, True, None),
    "message_react": ("message_react", 8, False, "idle"),
    "bubble_react": ("bubble_react", 6, False, "idle"),
    "blink": ("blink", 8, False, "idle"),
    "hover": ("hover", 5, True, None),
    "drag": ("drag", 4, True, None),
}

PREVIEW_STATE_ORDER = (
    "idle",
    "run_right",
    "run_left",
    "running",
    "waiting",
    "failed",
    "review",
    "waving",
    "jumping",
    "message_react",
    "bubble_react",
    "blink",
    "hover",
    "drag",
)
OPTIONAL_PREVIEW_STATES = tuple(state for state in PREVIEW_STATE_ORDER if state != "idle")


@dataclass
class CustomPetPackage:
    root: Path
    name: str
    states: dict[str, dict[str, Any]]
    source_format: str


def _canonical_state_order(states: set[str]) -> list[str]:
    ordered = [state for state in PREVIEW_STATE_ORDER if state in states]
    ordered.extend(sorted(states.difference(PREVIEW_STATE_ORDER)))
    return ordered


def custom_pets_dir(base_dir: Path | None = None) -> Path:
    return (base_dir or state_dir()) / "custom-pets"


def current_selection_path(base_dir: Path | None = None) -> Path:
    return (base_dir or state_dir()) / CURRENT_SELECTION_FILE


def validate_pet_name(name: str) -> str:
    slug = str(name or "").strip().lower()
    if not SAFE_NAME_RE.fullmatch(slug):
        raise ValueError("custom pet name must use lowercase letters, numbers, '-' or '_' and start with a letter or number")
    return slug


def _ensure_inside(root: Path, child: Path) -> None:
    child.resolve().relative_to(root.resolve())


def _is_png(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(PNG_SIGNATURE)) == PNG_SIGNATURE
    except OSError:
        return False


def _load_metadata(root: Path) -> dict[str, Any]:
    path = root / CUSTOM_PET_METADATA
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{CUSTOM_PET_METADATA} must contain a JSON object")
    return data


def _state_dirs(root: Path, metadata: dict[str, Any]) -> tuple[Path, list[Path]]:
    candidates: list[Path] = []
    if (root / "sprites").is_dir():
        candidates.append(root / "sprites")
    if (root / "frames").is_dir():
        candidates.append(root / "frames")
    candidates.append(root)

    state_names = set(STATE_MAP)
    meta_states = metadata.get("states")
    if isinstance(meta_states, dict):
        state_names.update(str(key) for key in meta_states)

    for base in candidates:
        dirs = [base / state for state in sorted(state_names) if (base / state).is_dir()]
        if dirs:
            return base, dirs
    return root, []


def _frame_files(state_dir: Path) -> list[Path]:
    frames = []
    for item in sorted(state_dir.iterdir()):
        if item.is_file() and item.suffix.lower() == ".png":
            frames.append(item)
    return frames


def _state_config(state: str, frames: list[Path], metadata: dict[str, Any]) -> dict[str, Any]:
    hermes_state, fps, loop, fallback = STATE_MAP.get(state, (state, 4, True, None))
    meta_states = metadata.get("states") if isinstance(metadata.get("states"), dict) else {}
    raw_cfg = meta_states.get(state) or meta_states.get(hermes_state) or {}
    cfg: dict[str, Any] = {
        "fps": int(raw_cfg.get("fps", fps)) if isinstance(raw_cfg, dict) else fps,
        "loop": bool(raw_cfg.get("loop", loop)) if isinstance(raw_cfg, dict) else loop,
        "frames": [frame.name for frame in frames],
    }
    raw_fallback = raw_cfg.get("fallback") if isinstance(raw_cfg, dict) else fallback
    if raw_fallback:
        cfg["fallback"] = str(raw_fallback)
    elif fallback:
        cfg["fallback"] = fallback
    return cfg


def inspect_package(path: str | Path, *, name: str | None = None) -> CustomPetPackage:
    root = Path(path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"custom pet path must be a directory: {root}")

    metadata = _load_metadata(root)
    package_name = validate_pet_name(name or str(metadata.get("name") or root.name))
    sprites_base, dirs = _state_dirs(root, metadata)
    if not dirs:
        raise ValueError("custom pet package must contain sprites/<state>/, frames/<state>/, or state subfolders with PNG frames")

    states: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for state_dir in dirs:
        try:
            _ensure_inside(root, state_dir)
        except ValueError:
            errors.append(f"path escapes package root: {state_dir}")
            continue
        state = state_dir.name
        if state not in STATE_MAP and not SAFE_NAME_RE.fullmatch(state):
            errors.append(f"unsafe state folder name: {state}")
            continue
        frames = _frame_files(state_dir)
        if not frames:
            continue
        for frame in frames:
            try:
                _ensure_inside(root, frame)
            except ValueError:
                errors.append(f"path escapes package root: {frame}")
                continue
            if not SAFE_FRAME_RE.fullmatch(frame.name) or "/" in frame.name or "\\" in frame.name:
                errors.append(f"unsafe frame filename: {frame.relative_to(root)}")
            elif not _is_png(frame):
                errors.append(f"not a PNG file: {frame.relative_to(root)}")
        hermes_state = STATE_MAP.get(state, (state, 4, True, None))[0]
        states[hermes_state] = _state_config(state, frames, metadata)

    if "idle" not in states:
        errors.append("custom pet must include an idle state")
    if errors:
        raise ValueError("\n".join(errors))

    source_format = "hatch-pet" if sprites_base.name == "frames" and (root / "final").exists() else "custom-pet"
    return CustomPetPackage(root=root, name=package_name, states=states, source_format=source_format)


def _package_state_frame_paths(package: CustomPetPackage) -> dict[str, list[Path]]:
    metadata = _load_metadata(package.root)
    _, dirs = _state_dirs(package.root, metadata)
    paths: dict[str, list[Path]] = {}
    for state_dir in dirs:
        hermes_state = STATE_MAP.get(state_dir.name, (state_dir.name, 4, True, None))[0]
        if hermes_state not in package.states:
            continue
        source_frames = {frame.name: frame for frame in _frame_files(state_dir)}
        ordered_paths = []
        for frame_name in package.states[hermes_state].get("frames", []):
            frame = source_frames.get(str(frame_name))
            if frame and frame.is_file():
                ordered_paths.append(frame)
        if not ordered_paths:
            ordered_paths = _frame_files(state_dir)
        paths[hermes_state] = ordered_paths
    return paths


def custom_pet_preview_summary(package: CustomPetPackage) -> dict[str, Any]:
    """Return a display-friendly custom pet state summary."""
    frame_paths = _package_state_frame_paths(package)
    states = []
    for state in _canonical_state_order(set(package.states)):
        cfg = package.states[state]
        frames = [str(path) for path in frame_paths.get(state, [])]
        states.append(
            {
                "name": state,
                "fps": int(cfg.get("fps", 4) or 4),
                "loop": bool(cfg.get("loop", True)),
                "fallback": str(cfg.get("fallback") or ""),
                "frame_count": len(cfg.get("frames", [])),
                "frames": list(cfg.get("frames", [])),
                "frame_paths": frames,
            }
        )
    missing = [state for state in OPTIONAL_PREVIEW_STATES if state not in package.states]
    return {
        "name": package.name,
        "path": str(package.root),
        "source_format": package.source_format,
        "states": states,
        "missing_optional_states": missing,
        "missing_fallback": "idle",
    }


def render_custom_pet_preview_html(package: CustomPetPackage) -> str:
    """Render a standalone HTML animation preview for a validated package."""
    summary = custom_pet_preview_summary(package)
    frames_by_state: dict[str, list[dict[str, str]]] = {}
    for state in summary["states"]:
        frame_items = []
        for path_text in state["frame_paths"]:
            path = Path(path_text)
            try:
                data_uri = "data:image/png;base64," + b64encode(path.read_bytes()).decode("ascii")
            except OSError:
                continue
            frame_items.append({"name": path.name, "src": data_uri})
        frames_by_state[state["name"]] = frame_items

    state_cards = []
    for state in summary["states"]:
        fallback = state["fallback"] or "none"
        first_frame = frames_by_state.get(state["name"], [{}])[0].get("src", "")
        state_cards.append(
            f"""
      <section class="state-card" data-state="{escape(state['name'])}">
        <div class="sprite-stage">
          <img alt="{escape(state['name'])} preview" src="{first_frame}" data-frame-index="0">
        </div>
        <h2>{escape(state['name'])}</h2>
        <p>{state['frame_count']} frame(s), {state['fps']} fps, {'loop' if state['loop'] else 'one-shot'}, fallback: {escape(fallback)}</p>
      </section>"""
        )

    missing = ", ".join(summary["missing_optional_states"]) or "none"
    frames_json = json.dumps(frames_by_state)
    state_meta_json = json.dumps({state["name"]: state for state in summary["states"]})
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hermes custom pet preview: {escape(package.name)}</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #101416;
      color: #edf5f2;
    }}
    body {{
      margin: 0;
      padding: 28px;
    }}
    header {{
      max-width: 960px;
      margin: 0 auto 24px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    .meta {{
      margin: 0;
      color: #b8c9c3;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      max-width: 960px;
      margin: 0 auto;
    }}
    .state-card {{
      border: 1px solid #334541;
      border-radius: 8px;
      background: #18211f;
      padding: 14px;
    }}
    .sprite-stage {{
      display: grid;
      place-items: center;
      height: 168px;
      border-radius: 6px;
      background:
        linear-gradient(45deg, #22302c 25%, transparent 25%),
        linear-gradient(-45deg, #22302c 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, #22302c 75%),
        linear-gradient(-45deg, transparent 75%, #22302c 75%);
      background-size: 24px 24px;
      background-position: 0 0, 0 12px, 12px -12px, -12px 0;
    }}
    img {{
      max-width: 144px;
      max-height: 144px;
      image-rendering: pixelated;
    }}
    h2 {{
      margin: 12px 0 4px;
      font-size: 16px;
      letter-spacing: 0;
    }}
    p {{
      margin: 0;
      color: #b8c9c3;
      font-size: 14px;
      line-height: 1.45;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(package.name)}</h1>
    <p class="meta">Package: {escape(str(package.root))}<br>Format: {escape(package.source_format)}<br>Missing optional states: {escape(missing)}. Missing states fall back to idle in the overlay.</p>
  </header>
  <main class="grid">
    {''.join(state_cards)}
  </main>
  <script>
    const framesByState = {frames_json};
    const stateMeta = {state_meta_json};
    for (const card of document.querySelectorAll('.state-card')) {{
      const state = card.dataset.state;
      const img = card.querySelector('img');
      const frames = framesByState[state] || [];
      const meta = stateMeta[state] || {{}};
      if (!img || frames.length === 0) continue;
      let index = 0;
      const interval = Math.max(80, Math.round(1000 / Math.max(1, Number(meta.fps || 4))));
      window.setInterval(() => {{
        if (!meta.loop && index >= frames.length - 1) return;
        index = (index + 1) % frames.length;
        img.src = frames[index].src;
        img.dataset.frameIndex = String(index);
      }}, interval);
    }}
  </script>
</body>
</html>
"""


def _copy_package_frames(package: CustomPetPackage, dest: Path) -> None:
    metadata = _load_metadata(package.root)
    source_base, dirs = _state_dirs(package.root, metadata)
    dest_sprites = dest / "sprites"
    for source_state_dir in dirs:
        source_state = source_state_dir.name
        hermes_state = STATE_MAP.get(source_state, (source_state, 4, True, None))[0]
        if hermes_state not in package.states:
            continue
        target_state_dir = dest_sprites / hermes_state
        target_state_dir.mkdir(parents=True, exist_ok=True)
        frame_names: list[str] = []
        for index, frame in enumerate(_frame_files(source_state_dir)):
            target_name = frame.name
            if frame.stem.isdigit() or target_name not in package.states[hermes_state]["frames"]:
                target_name = f"{hermes_state}_{index:02d}.png"
            shutil.copy2(frame, target_state_dir / target_name)
            frame_names.append(target_name)
        package.states[hermes_state]["frames"] = frame_names


def write_package_metadata(dest: Path, package: CustomPetPackage) -> dict[str, Any]:
    metadata = {
        "version": PACKAGE_VERSION,
        "name": package.name,
        "source_format": package.source_format,
        "states": package.states,
    }
    (dest / CUSTOM_PET_METADATA).write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata


def import_package(path: str | Path, *, name: str, base_dir: Path | None = None) -> Path:
    package = inspect_package(path, name=name)
    dest = custom_pets_dir(base_dir) / package.name
    if dest.exists():
        raise ValueError(f"custom pet already exists: {package.name}")
    dest.mkdir(parents=True, exist_ok=False)
    try:
        _copy_package_frames(package, dest)
        for optional in ("contact-sheet.png", "README.md"):
            source = package.root / optional
            if source.is_file():
                shutil.copy2(source, dest / optional)
        write_package_metadata(dest, package)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest


def list_custom_pets(base_dir: Path | None = None) -> list[dict[str, Any]]:
    root = custom_pets_dir(base_dir)
    if not root.exists():
        return []
    pets = []
    current = current_custom_pet(base_dir)
    for item in sorted(root.iterdir()):
        if not item.is_dir():
            continue
        try:
            package = inspect_package(item)
        except Exception as exc:
            pets.append({"name": item.name, "path": str(item), "valid": False, "error": str(exc)})
        else:
            pets.append({
                "name": package.name,
                "path": str(item),
                "valid": True,
                "states": sorted(package.states),
                "current": bool(current and current.get("name") == package.name),
            })
    return pets


def set_current_custom_pet(name: str, base_dir: Path | None = None) -> dict[str, Any]:
    slug = validate_pet_name(name)
    package_dir = custom_pets_dir(base_dir) / slug
    package = inspect_package(package_dir, name=slug)
    selection = {
        "name": package.name,
        "path": str(package_dir),
    }
    path = current_selection_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return custom_pet_event_payload(base_dir)


def clear_current_custom_pet(base_dir: Path | None = None) -> bool:
    path = current_selection_path(base_dir)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def current_custom_pet(base_dir: Path | None = None) -> dict[str, Any] | None:
    path = current_selection_path(base_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        name = validate_pet_name(str(data.get("name") or ""))
        package_dir = custom_pets_dir(base_dir) / name
        inspect_package(package_dir, name=name)
    except Exception:
        return None
    return {"name": name, "path": str(package_dir)}


def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return False


def overlay_accessible_path(path: Path) -> str:
    if not _is_wsl():
        return str(path)
    try:
        result = subprocess.run(
            ["wslpath", "-w", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return str(path)
    converted = result.stdout.strip()
    return converted or str(path)


def custom_pet_event_payload(base_dir: Path | None = None) -> dict[str, Any] | None:
    current = current_custom_pet(base_dir)
    if not current:
        return None
    package_dir = Path(current["path"])
    package = inspect_package(package_dir, name=current["name"])
    return {
        "name": package.name,
        "path": str(package_dir),
        "overlay_path": overlay_accessible_path(package_dir),
        "manifest": {
            "version": PACKAGE_VERSION,
            "states": package.states,
        },
    }


def remove_custom_pet(name: str, base_dir: Path | None = None) -> None:
    slug = validate_pet_name(name)
    current = current_custom_pet(base_dir)
    package_dir = custom_pets_dir(base_dir) / slug
    if not package_dir.exists():
        raise ValueError(f"custom pet not found: {slug}")
    shutil.rmtree(package_dir)
    if current and current.get("name") == slug:
        try:
            current_selection_path(base_dir).unlink()
        except FileNotFoundError:
            pass
