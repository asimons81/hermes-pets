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
from pathlib import Path, PureWindowsPath
from typing import Any

from hermes_pet.prefs import state_dir

PACKAGE_VERSION = 1
CURRENT_SELECTION_FILE = "custom-pet-current.json"
CUSTOM_PET_METADATA = "custom-pet.json"
SAFE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SAFE_FRAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.png$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_CODEX_SPRITESHEET_PIXELS = 32_000_000

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


@dataclass(frozen=True)
class CodexPetCandidate:
    """Importable pet package produced by Codex pet tooling."""

    slug: str
    path: Path
    name: str
    source_format: str
    source_kind: str
    modified_at: float
    states: tuple[str, ...]


CODEX_PET_PACKAGE_ROOT = Path("output/hermes-pet-hatch")
CODEX_HATCH_RUN_ROOT = Path("output/hatch-pet-runs")
CODEX_APP_PETS_ROOT = Path(".codex/pets")
CODEX_LATEST_ALIASES = {"", "latest", "newest", "last"}
CODEX_APP_ATLAS_COLUMNS = 8
CODEX_APP_ATLAS_ROWS = 9
CODEX_APP_STATE_ROWS = (
    ("idle", 0, 6),
    ("running-right", 1, 8),
    ("running-left", 2, 8),
    ("waving", 3, 4),
    ("jumping", 4, 5),
    ("failed", 5, 8),
    ("waiting", 6, 6),
    ("running", 7, 6),
    ("review", 8, 6),
)


def repo_root(default: Path | None = None) -> Path:
    """Return the source checkout root used for optional repo-local output discovery."""

    if default is not None:
        return Path(default).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _candidate_modified_at(path: Path) -> float:
    probe_paths = [
        path,
        path / "pet.json",
        path / "spritesheet.webp",
        path / CUSTOM_PET_METADATA,
        path / "qa" / "run-summary.json",
        path / "qa" / "review.json",
        path / "final" / "validation.json",
        path / "frames" / "frames-manifest.json",
    ]
    mtimes = []
    for item in probe_paths:
        try:
            mtimes.append(item.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes) if mtimes else 0.0


def _load_codex_app_pet_metadata(path: Path) -> dict[str, Any] | None:
    metadata_path = path / "pet.json"
    spritesheet_path = path / "spritesheet.webp"
    if not metadata_path.is_file() or not spritesheet_path.is_file():
        return None
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _resolve_codex_pet_child_path(root: Path, value: object, *, default: str) -> Path:
    """Resolve a Codex metadata path, requiring it to stay inside the pet root."""

    raw = default if value is None else str(value).strip()
    if not raw or "\x00" in raw:
        raise ValueError("Codex pet metadata path is empty")
    if raw.startswith("\\\\") or re.match(r"^[A-Za-z]:[\\/]", raw):
        raise ValueError("Codex pet metadata path must be relative")

    windows_candidate = PureWindowsPath(raw)
    if windows_candidate.is_absolute() or windows_candidate.drive:
        raise ValueError("Codex pet metadata path must be relative")

    candidate = Path(raw)
    if candidate.is_absolute():
        raise ValueError("Codex pet metadata path must be relative")

    parts = windows_candidate.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Codex pet metadata path must not contain traversal segments")

    root_resolved = root.resolve()
    resolved = root_resolved.joinpath(*parts).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("Codex pet metadata path escapes the pet directory") from exc
    return resolved


def _codex_app_pet_candidate(path: Path) -> CodexPetCandidate | None:
    metadata = _load_codex_app_pet_metadata(path)
    if metadata is None:
        return None
    raw_name = metadata.get("id") or metadata.get("name") or metadata.get("displayName") or path.name
    try:
        slug = validate_pet_name(str(raw_name))
    except ValueError:
        return None
    display_name = str(metadata.get("displayName") or slug)
    return CodexPetCandidate(
        slug=slug,
        path=path.resolve(),
        name=slug,
        source_format="codex-pet",
        source_kind="codex-pet",
        modified_at=_candidate_modified_at(path),
        states=tuple(STATE_MAP[state][0] for state, _, _ in CODEX_APP_STATE_ROWS),
    )


def _codex_candidate(path: Path, *, slug: str, source_kind: str) -> CodexPetCandidate | None:
    if source_kind == "codex-pet":
        return _codex_app_pet_candidate(path)
    try:
        package = inspect_package(path)
    except Exception:
        return None
    return CodexPetCandidate(
        slug=validate_pet_name(slug),
        path=path.resolve(),
        name=package.name,
        source_format=package.source_format,
        source_kind=source_kind,
        modified_at=_candidate_modified_at(path),
        states=tuple(_canonical_state_order(set(package.states))),
    )


def codex_candidate_to_dict(candidate: CodexPetCandidate) -> dict[str, Any]:
    return {
        "slug": candidate.slug,
        "name": candidate.name,
        "path": str(candidate.path),
        "source_format": candidate.source_format,
        "source_kind": candidate.source_kind,
        "modified_at": candidate.modified_at,
        "states": list(candidate.states),
    }


def _windows_user_codex_pet_dirs() -> list[Path]:
    users_root = Path("/mnt/c/Users")
    if not users_root.is_dir():
        return []
    dirs: list[Path] = []
    try:
        users = sorted(users_root.iterdir())
    except OSError:
        return []
    for user_dir in users:
        if not user_dir.is_dir() or user_dir.name.lower() in {"public", "default", "default user", "all users"}:
            continue
        pets_dir = user_dir / CODEX_APP_PETS_ROOT
        if pets_dir.is_dir():
            dirs.append(pets_dir)
    return dirs


def codex_app_pets_dirs() -> list[Path]:
    """Return likely Codex desktop pet stores, preferring explicit/current-user locations."""

    candidates: list[Path] = []
    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        candidates.append(Path(env_home).expanduser() / "pets")
    candidates.append(Path.home() / CODEX_APP_PETS_ROOT)
    if os.environ.get("HERMES_PET_DISABLE_WINDOWS_CODEX_SCAN") not in {"1", "true", "yes"}:
        candidates.extend(_windows_user_codex_pet_dirs())
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not path.is_dir():
            continue
        unique.append(path)
        seen.add(resolved)
    return unique


def _discover_codex_app_pet_candidates() -> list[CodexPetCandidate]:
    candidates: list[CodexPetCandidate] = []
    seen: set[Path] = set()
    for pets_dir in codex_app_pets_dirs():
        try:
            pets_root = pets_dir.resolve()
            items = sorted(pets_dir.iterdir())
        except OSError:
            continue
        for item in items:
            if not item.is_dir() or item.name.startswith(".") or ".backup" in item.name:
                continue
            try:
                resolved = item.resolve()
                resolved.relative_to(pets_root)
            except (OSError, ValueError):
                continue
            if resolved in seen:
                continue
            candidate = _codex_app_pet_candidate(item)
            if candidate:
                candidates.append(candidate)
                seen.add(resolved)
    return candidates


def _discover_repo_output_candidates(repo: Path | None = None) -> list[CodexPetCandidate]:
    root = repo_root(repo)
    candidates: list[CodexPetCandidate] = []
    seen: set[Path] = set()

    package_root = root / CODEX_PET_PACKAGE_ROOT
    if package_root.is_dir():
        try:
            package_root_resolved = package_root.resolve()
        except OSError:
            package_root_resolved = None
        for item in sorted(package_root.iterdir()):
            if not item.is_dir() or package_root_resolved is None:
                continue
            for path, source_kind in ((item / "package", "codex-package"), (item, "codex-package")):
                try:
                    resolved = path.resolve()
                    resolved.relative_to(package_root_resolved)
                except (OSError, ValueError):
                    continue
                if resolved in seen or not path.is_dir():
                    continue
                candidate = _codex_candidate(path, slug=item.name, source_kind=source_kind)
                if candidate:
                    candidates.append(candidate)
                    seen.add(resolved)
                    break

    hatch_root = root / CODEX_HATCH_RUN_ROOT
    if hatch_root.is_dir():
        try:
            hatch_root_resolved = hatch_root.resolve()
        except OSError:
            hatch_root_resolved = None
        for item in sorted(hatch_root.iterdir()):
            if not item.is_dir() or hatch_root_resolved is None:
                continue
            try:
                resolved = item.resolve()
                resolved.relative_to(hatch_root_resolved)
            except (OSError, ValueError):
                continue
            if resolved in seen:
                continue
            candidate = _codex_candidate(item, slug=item.name, source_kind="hatch-pet-run")
            if candidate:
                candidates.append(candidate)
                seen.add(resolved)
    return candidates


def _sort_codex_candidates(candidates: list[CodexPetCandidate]) -> list[CodexPetCandidate]:
    priority = {"codex-pet": 0, "codex-package": 1, "hatch-pet-run": 2, "direct-path": 3}
    return sorted(candidates, key=lambda item: (priority.get(item.source_kind, 9), -item.modified_at, item.slug))


def discover_codex_pet_candidates(repo: Path | None = None, *, include_repo_output: bool = False) -> list[CodexPetCandidate]:
    """Find valid Codex desktop pets, optionally including repo-local hatch outputs."""

    candidates = _discover_codex_app_pet_candidates()
    if include_repo_output:
        existing = {candidate.path for candidate in candidates}
        for candidate in _discover_repo_output_candidates(repo):
            if candidate.path not in existing:
                candidates.append(candidate)
    return _sort_codex_candidates(candidates)


def resolve_codex_pet_candidate(
    selector: str | Path | None = None,
    *,
    repo: Path | None = None,
    include_repo_output: bool = False,
) -> CodexPetCandidate:
    """Resolve a Codex pet selector: latest, slug/name, or direct path."""

    raw_selector = str(selector or "latest").strip()
    root = repo_root(repo)
    if raw_selector not in CODEX_LATEST_ALIASES:
        candidate_path = Path(raw_selector).expanduser()
        if not candidate_path.is_absolute():
            candidate_path = (root / candidate_path).resolve()
        if candidate_path.exists():
            candidate = _codex_app_pet_candidate(candidate_path) or _codex_candidate(
                candidate_path,
                slug=candidate_path.name,
                source_kind="direct-path",
            )
            if candidate is None:
                raise ValueError(f"Codex pet path is not a valid Codex pet, package, or hatch-pet run: {candidate_path}")
            return candidate

    candidates = discover_codex_pet_candidates(root, include_repo_output=include_repo_output)
    if not candidates:
        searched = [str(path) for path in codex_app_pets_dirs()]
        if include_repo_output:
            searched.extend([str(root / CODEX_PET_PACKAGE_ROOT), str(root / CODEX_HATCH_RUN_ROOT)])
        raise ValueError(f"No importable Codex pets found. Searched: {', '.join(searched) or 'no Codex pet dirs found'}")

    normalized = raw_selector.lower()
    if normalized in CODEX_LATEST_ALIASES:
        return candidates[0]

    matches = [item for item in candidates if normalized in {item.slug.lower(), item.name.lower(), item.path.name.lower()}]
    if not matches:
        available = ", ".join(item.slug for item in candidates[:10])
        raise ValueError(f"No Codex pet matches '{raw_selector}'. Available: {available or 'none'}")
    return _sort_codex_candidates(matches)[0]


def _copy_codex_app_pet(candidate: CodexPetCandidate, dest: Path, installed_name: str) -> None:
    metadata = _load_codex_app_pet_metadata(candidate.path)
    if metadata is None:
        raise ValueError(f"invalid Codex pet store package: {candidate.path}")
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("Pillow is required to import Codex spritesheet pets") from exc

    spritesheet = _resolve_codex_pet_child_path(candidate.path, metadata.get("spritesheetPath"), default="spritesheet.webp")
    if not spritesheet.is_file():
        raise ValueError(f"missing Codex pet spritesheet: {spritesheet}")
    with Image.open(spritesheet) as loaded_image:
        width, height = loaded_image.size
        if width <= 0 or height <= 0 or width * height > MAX_CODEX_SPRITESHEET_PIXELS:
            raise ValueError(f"unsafe Codex spritesheet size: {width}x{height}")
        if width % CODEX_APP_ATLAS_COLUMNS or height % CODEX_APP_ATLAS_ROWS:
            raise ValueError(f"unexpected Codex spritesheet size: {width}x{height}")
        image = loaded_image.convert("RGBA")
    cell_width = image.width // CODEX_APP_ATLAS_COLUMNS
    cell_height = image.height // CODEX_APP_ATLAS_ROWS

    states: dict[str, dict[str, Any]] = {}
    sprites_root = dest / "sprites"
    for hatch_state, row, frame_count in CODEX_APP_STATE_ROWS:
        hermes_state, fps, loop, fallback = STATE_MAP[hatch_state]
        state_dir = sprites_root / hermes_state
        state_dir.mkdir(parents=True, exist_ok=True)
        frame_names: list[str] = []
        for index in range(frame_count):
            frame_name = f"{hermes_state}_{index:02d}.png"
            crop = image.crop((index * cell_width, row * cell_height, (index + 1) * cell_width, (row + 1) * cell_height))
            crop.save(state_dir / frame_name)
            frame_names.append(frame_name)
        cfg: dict[str, Any] = {"fps": fps, "loop": loop, "frames": frame_names}
        if fallback:
            cfg["fallback"] = fallback
        states[hermes_state] = cfg

    package = CustomPetPackage(root=dest, name=installed_name, states=states, source_format="codex-pet")
    write_package_metadata(dest, package)
    shutil.copy2(candidate.path / "pet.json", dest / "codex-pet.json")
    shutil.copy2(spritesheet, dest / "spritesheet.webp")


def import_codex_pet(
    selector: str | Path | None = None,
    *,
    name: str | None = None,
    base_dir: Path | None = None,
    repo: Path | None = None,
    replace: bool = False,
    include_repo_output: bool = False,
) -> dict[str, Any]:
    """Import a Codex-generated custom pet into the active Hermes Pets state dir."""

    candidate = resolve_codex_pet_candidate(selector, repo=repo, include_repo_output=include_repo_output)
    installed_name = validate_pet_name(name or candidate.name or candidate.slug)
    dest = custom_pets_dir(base_dir) / installed_name
    if dest.exists():
        if not replace:
            raise ValueError(f"custom pet already exists: {installed_name}")
        remove_custom_pet(installed_name, base_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if candidate.source_kind == "codex-pet":
        dest.mkdir(parents=True, exist_ok=False)
        try:
            _copy_codex_app_pet(candidate, dest, installed_name)
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)
            raise
        imported_path = dest
    else:
        imported_path = import_package(candidate.path, name=installed_name, base_dir=base_dir)
    return {
        "candidate": codex_candidate_to_dict(candidate),
        "imported": {"name": installed_name, "path": str(imported_path)},
    }


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
        optional_sources = {
            "contact-sheet.png": (package.root / "contact-sheet.png", package.root / "qa" / "contact-sheet.png"),
            "README.md": (package.root / "README.md",),
        }
        for target_name, sources in optional_sources.items():
            for source in sources:
                if source.is_file():
                    shutil.copy2(source, dest / target_name)
                    break
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


def activate_custom_pet(name: str, base_dir: Path | None = None) -> dict[str, Any]:
    """Make an installed custom pet the actual active pet, not just an overlay visual."""

    root = base_dir or state_dir()
    slug = validate_pet_name(name)
    package_dir = custom_pets_dir(root) / slug
    package = inspect_package(package_dir, name=slug)

    from hermes_pet.engine import CUSTOM_PET_SPECIES, STATS, Pet, load_pet, save_pet

    existing = load_pet("", state_dir=root)
    if existing and existing.species == CUSTOM_PET_SPECIES and existing.name == package.name:
        pet = existing
    else:
        pet = Pet(
            name=package.name,
            species=CUSTOM_PET_SPECIES,
            variant="custom",
            hat="none",
            stats={stat: 1 for stat in STATS},
        )
    save_pet(pet, state_dir=root)
    payload = set_current_custom_pet(package.name, root)
    return {"pet": pet, "custom_pet": payload}


def clear_active_custom_pet(base_dir: Path | None = None) -> bool:
    """Clear custom selection and remove custom-only active pet state if needed."""

    root = base_dir or state_dir()
    cleared = clear_current_custom_pet(root)
    try:
        from hermes_pet.engine import CUSTOM_PET_SPECIES, delete_pet, load_pet

        pet = load_pet("", state_dir=root)
        if pet and pet.species == CUSTOM_PET_SPECIES:
            delete_pet(root)
    except Exception:
        pass
    return cleared


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
