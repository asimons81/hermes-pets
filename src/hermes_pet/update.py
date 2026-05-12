"""Guarded update workflow for Hermes Pets."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
import shutil
import subprocess
import sys
from typing import TextIO


PACKAGE_NAME = "hermes-pet"
STATE_DIR_GUIDANCE = "~/.hermes_pet"


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class PythonInstallInfo:
    version: str
    package_location: Path
    distribution_location: Path | None
    editable: bool | None
    source_url: str


@dataclass(frozen=True)
class GitInfo:
    root: Path | None
    branch: str
    commit: str
    remote_url: str
    upstream: str
    dirty: bool
    changed_files: tuple[str, ...]


@dataclass(frozen=True)
class OverlayInfo:
    directory: Path | None
    package_json_exists: bool
    lockfile: str
    node_modules_exists: bool
    package_manager: str
    package_manager_available: bool


@dataclass(frozen=True)
class PackagingInfo:
    pyproject: bool
    setup_py: bool
    setup_cfg: bool


@dataclass(frozen=True)
class InstallInfo:
    python: PythonInstallInfo
    git: GitInfo
    overlay: OverlayInfo
    packaging: PackagingInfo
    detected_mode: str
    automatic_update_available: bool


@dataclass(frozen=True)
class UpdateOptions:
    check: bool
    dry_run: bool
    yes: bool
    no_install: bool
    verbose: bool


@dataclass(frozen=True)
class UpstreamState:
    state: str
    ahead: int
    behind: int


@dataclass(frozen=True)
class DependencyResult:
    ok: bool
    skipped: bool = False


def _run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> CommandResult:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return CommandResult(tuple(args), 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(tuple(args), 124, stdout, stderr or f"Timed out after {timeout} seconds")
    except OSError as exc:
        return CommandResult(tuple(args), 1, "", str(exc))
    return CommandResult(tuple(args), int(result.returncode), result.stdout or "", result.stderr or "")


def _line(value: str) -> str:
    return " ".join(str(value or "").strip().splitlines()).strip()


def _print_section(title: str, out: TextIO) -> None:
    print(file=out)
    print(title, file=out)
    print("-" * len(title), file=out)


def _print_kv(label: str, value: object, out: TextIO) -> None:
    print(f"{label}: {value}", file=out)


def _read_pyproject_version(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="ignore")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("version"):
            _, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if value:
                return value
    return None


def current_version(package_dir: Path | None = None) -> str:
    package_dir = Path(package_dir or __file__).resolve()
    # Prefer source truth when inside a checkout (editable or source run).
    # The repo root is two levels above src/hermes_pet/update.py.
    candidates: list[Path] = []
    if len(package_dir.parents) >= 3:
        candidates.append(package_dir.parents[2] / "pyproject.toml")
    candidates.append(Path.cwd() / "pyproject.toml")

    for candidate in candidates:
        version = _read_pyproject_version(candidate)
        if version is not None:
            return version

    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        pass

    return "unknown"


def _python_environment_hint(executable: Path) -> str:
    text = str(executable)
    if "/.local/share/uv/tools/" in text:
        return "uv tool environment"
    if "/.local/pipx/venvs/" in text or "\\pipx\\venvs\\" in text:
        return "pipx environment"
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        return f"virtual environment ({virtual_env})"
    if executable.parent.name in {"bin", "Scripts"}:
        parent = executable.parent.parent
        if (parent / "pyvenv.cfg").is_file():
            return f"virtual environment ({parent})"
    return "system or unknown Python environment"


def _distribution_info(package_location: Path) -> tuple[Path | None, bool | None, str]:
    try:
        dist = metadata.distribution(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return None, None, ""

    location: Path | None = None
    try:
        location = Path(dist.locate_file("")).resolve()
    except Exception:
        location = None

    editable: bool | None = None
    source_url = ""
    try:
        direct_url = dist.read_text("direct_url.json")
    except Exception:
        direct_url = None
    if direct_url:
        try:
            data = json.loads(direct_url)
        except json.JSONDecodeError:
            data = {}
        dir_info = data.get("dir_info") if isinstance(data, dict) else {}
        if isinstance(dir_info, dict) and "editable" in dir_info:
            editable = bool(dir_info.get("editable"))
        url = data.get("url") if isinstance(data, dict) else ""
        if isinstance(url, str):
            source_url = url

    if editable is None and location is not None:
        try:
            if package_location.is_relative_to(location):
                editable = False
        except ValueError:
            pass

    return location, editable, source_url


def _git(root: Path, *args: str, timeout: float | None = 20.0) -> CommandResult:
    return _run_command(["git", *args], cwd=root, timeout=timeout)


def _find_git_root(package_location: Path) -> Path | None:
    result = _run_command(["git", "rev-parse", "--show-toplevel"], cwd=package_location, timeout=5.0)
    if result.returncode != 0:
        return None
    text = _line(result.stdout)
    if not text:
        return None
    root = Path(text).expanduser().resolve()
    if not (root / ".git").exists():
        return None
    if not ((root / "pyproject.toml").exists() and (root / "src" / "hermes_pet").exists()):
        return None
    source_package = (root / "src" / "hermes_pet").resolve()
    try:
        package_location.relative_to(source_package)
    except ValueError:
        return None
    return root


def _git_text(root: Path, *args: str) -> str:
    result = _git(root, *args)
    if result.returncode != 0:
        return ""
    return _line(result.stdout)


def _collect_git_info(root: Path | None) -> GitInfo:
    if root is None:
        return GitInfo(None, "not detected", "not detected", "not detected", "not detected", False, ())

    branch = _git_text(root, "branch", "--show-current") or _git_text(root, "rev-parse", "--abbrev-ref", "HEAD")
    commit = _git_text(root, "rev-parse", "HEAD") or "unknown"
    remote_url = _git_text(root, "config", "--get", "remote.origin.url") or "not configured"
    upstream = _git_text(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") or "not configured"
    status = _git(root, "status", "--porcelain")
    changed = tuple(line for line in status.stdout.splitlines() if line.strip()) if status.returncode == 0 else ()
    return GitInfo(
        root=root,
        branch=branch or "detached",
        commit=commit,
        remote_url=remote_url,
        upstream=upstream,
        dirty=bool(changed),
        changed_files=changed,
    )


def select_package_manager(overlay_dir: Path | None) -> tuple[str, str, bool]:
    if overlay_dir is None:
        return "not detected", "none", False
    lock_priority = [
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("package-lock.json", "npm"),
    ]
    for lockfile, manager in lock_priority:
        if (overlay_dir / lockfile).is_file():
            return manager, lockfile, bool(shutil.which(manager))
    return "npm", "none", bool(shutil.which("npm"))


def _collect_overlay_info(root: Path | None, package_location: Path) -> OverlayInfo:
    candidates: list[Path] = []
    if root is not None:
        candidates.append(root / "overlay")
    candidates.append(package_location / "overlay")

    overlay_dir = next((path for path in candidates if path.is_dir()), None)
    package_json_exists = bool(overlay_dir and (overlay_dir / "package.json").is_file())
    manager, lockfile, available = select_package_manager(overlay_dir)
    return OverlayInfo(
        directory=overlay_dir,
        package_json_exists=package_json_exists,
        lockfile=lockfile,
        node_modules_exists=bool(overlay_dir and (overlay_dir / "node_modules").is_dir()),
        package_manager=manager,
        package_manager_available=available,
    )


def _collect_packaging_info(root: Path | None, package_location: Path) -> PackagingInfo:
    if root is not None:
        base = root
    elif len(package_location.parents) >= 3:
        base = package_location.parents[2]
    else:
        base = package_location
    return PackagingInfo(
        pyproject=(base / "pyproject.toml").is_file(),
        setup_py=(base / "setup.py").is_file(),
        setup_cfg=(base / "setup.cfg").is_file(),
    )


def collect_install_info(package_dir: Path | None = None) -> InstallInfo:
    package_location = Path(package_dir or Path(__file__).resolve().parent).resolve()
    version = current_version(package_location)
    distribution_location, editable, source_url = _distribution_info(package_location)
    git_root = _find_git_root(package_location)
    git_info = _collect_git_info(git_root)
    overlay = _collect_overlay_info(git_root, package_location)
    packaging = _collect_packaging_info(git_root, package_location)

    mode_parts: list[str] = []
    if git_root is not None:
        mode_parts.append("git checkout")
    if editable is True:
        mode_parts.append("editable Python package")
    elif editable is False and distribution_location is not None:
        mode_parts.append("normal Python package")
    elif git_root is not None:
        mode_parts.append("source checkout")

    if overlay.package_json_exists:
        state = "present" if overlay.node_modules_exists else "missing"
        mode_parts.append(f"Electron overlay dependencies {state}")

    detected_mode = "; ".join(mode_parts) if mode_parts else "unknown install mode"
    return InstallInfo(
        python=PythonInstallInfo(
            version=version,
            package_location=package_location,
            distribution_location=distribution_location,
            editable=editable,
            source_url=source_url,
        ),
        git=git_info,
        overlay=overlay,
        packaging=packaging,
        detected_mode=detected_mode,
        automatic_update_available=git_root is not None,
    )


def _print_detection(info: InstallInfo, out: TextIO, *, verbose: bool = False) -> None:
    _print_section("Install Detection", out)
    _print_kv("Detected install mode", info.detected_mode, out)
    automatic = "available for this git checkout" if info.automatic_update_available else "unavailable for this install mode"
    _print_kv("Automatic update", automatic, out)
    _print_kv("Python executable", sys.executable, out)
    _print_kv("Python environment", _python_environment_hint(Path(sys.executable)), out)
    _print_kv("Package install location", info.python.package_location, out)
    if info.python.distribution_location:
        _print_kv("Distribution location", info.python.distribution_location, out)
    editable = "unknown" if info.python.editable is None else str(info.python.editable).lower()
    _print_kv("Editable Python install", editable, out)
    if info.python.source_url:
        _print_kv("Package source", info.python.source_url, out)
    if verbose:
        _print_kv("Direct URL source", info.python.source_url or "not recorded", out)
        _print_kv("State directory inspection", f"skipped by update; {STATE_DIR_GUIDANCE} is never touched", out)


def _print_current_version(info: InstallInfo, out: TextIO) -> None:
    _print_section("Current Version", out)
    _print_kv("Hermes Pets version", info.python.version, out)


def _print_git_status(info: InstallInfo, out: TextIO) -> None:
    _print_section("Git Status", out)
    git = info.git
    _print_kv("Git repo path", git.root or "not detected", out)
    _print_kv("Current git branch", git.branch, out)
    _print_kv("Current git commit", git.commit, out)
    _print_kv("Remote URL", git.remote_url, out)
    _print_kv("Upstream branch", git.upstream, out)
    _print_kv("Dirty working tree", "yes" if git.dirty else "no", out)
    if git.changed_files:
        print("Changed files:", file=out)
        for item in git.changed_files:
            print(f"  {item}", file=out)


def _print_project_status(info: InstallInfo, out: TextIO) -> None:
    _print_section("Project Files", out)
    overlay = info.overlay
    _print_kv("Electron overlay directory", overlay.directory or "not detected", out)
    _print_kv("overlay/package.json", "yes" if overlay.package_json_exists else "no", out)
    _print_kv("Overlay lockfile", overlay.lockfile, out)
    _print_kv("overlay/node_modules", "yes" if overlay.node_modules_exists else "no", out)
    _print_kv("Required package manager", overlay.package_manager, out)
    _print_kv("Package manager available", "yes" if overlay.package_manager_available else "no", out)
    _print_kv("pyproject.toml", "yes" if info.packaging.pyproject else "no", out)
    _print_kv("setup.py", "yes" if info.packaging.setup_py else "no", out)
    _print_kv("setup.cfg", "yes" if info.packaging.setup_cfg else "no", out)


def _print_preflight(info: InstallInfo, out: TextIO, *, verbose: bool = False) -> None:
    print("Hermes Pets Update", file=out)
    _print_detection(info, out, verbose=verbose)
    _print_current_version(info, out)
    _print_git_status(info, out)
    _print_project_status(info, out)


def _manual_guidance(info: InstallInfo, out: TextIO) -> None:
    print("Automatic update is unavailable for this install mode.", file=out)
    print("Suggested manual paths:", file=out)
    print("- For a git checkout: commit or stash local work, then run git fetch and git merge --ff-only.", file=out)
    print("- For a package install: reinstall with the same installer you originally used.", file=out)
    if info.python.source_url:
        print(f"- Recorded package source: {info.python.source_url}", file=out)
    else:
        print("- No package source URL was recorded for this install.", file=out)
    print(f"- Back up the actual {STATE_DIR_GUIDANCE} directory before risky manual recovery.", file=out)


def _print_update_plan(info: InstallInfo, options: UpdateOptions, out: TextIO) -> None:
    _print_section("Update Plan", out)
    if not info.automatic_update_available:
        _manual_guidance(info, out)
        return
    print("- Fetch remote metadata.", file=out)
    print("- Compare local HEAD with the configured upstream branch.", file=out)
    print("- If behind, update with fast-forward only.", file=out)
    if options.no_install:
        print("- Skip Python and JS dependency refresh because --no-install was passed.", file=out)
    else:
        py_cmd = _python_install_command(info)
        if py_cmd:
            print(f"- Refresh Python dependencies with: {_format_cmd(py_cmd)}", file=out)
        else:
            print("- Skip Python dependency refresh unless the install style is clear.", file=out)
        js_cmd = _js_install_command(info)
        if js_cmd:
            print(f"- Refresh Electron overlay dependencies with: {_format_cmd(js_cmd)}", file=out)
        else:
            print("- Skip Electron overlay dependency refresh if no package.json is present.", file=out)
    print("- Validate with hermes-pet --version.", file=out)
    print(f"- Doctor is detected but skipped by update so {STATE_DIR_GUIDANCE} is never modified.", file=out)


def _fetch(root: Path, out: TextIO) -> bool:
    result = _git(root, "fetch")
    if result.returncode == 0:
        print("Fetched remote metadata.", file=out)
        return True
    print("Could not fetch remote metadata.", file=out)
    _print_command_failure(result, out)
    return False


def _compare_upstream(root: Path, upstream: str) -> UpstreamState | None:
    result = _git(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
    if result.returncode != 0:
        return None
    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return None
    try:
        ahead = int(parts[0])
        behind = int(parts[1])
    except ValueError:
        return None
    if ahead and behind:
        state = "diverged"
    elif ahead:
        state = "ahead"
    elif behind:
        state = "behind"
    else:
        state = "current"
    return UpstreamState(state, ahead=ahead, behind=behind)


def _print_upstream_state(state: UpstreamState | None, out: TextIO) -> None:
    _print_section("Remote Comparison", out)
    if state is None:
        print("Could not compare HEAD with upstream.", file=out)
        return
    print(f"Repository state: {state.state}", file=out)
    print(f"Commits ahead: {state.ahead}", file=out)
    print(f"Commits behind: {state.behind}", file=out)


def _check_result_line(state: UpstreamState | None) -> str:
    if state is None:
        return "blocked; upstream comparison failed"
    if state.state == "current":
        return "current; no update is available"
    if state.state == "behind":
        return "update available; a normal update can fast-forward if the working tree remains clean"
    if state.state == "ahead":
        return "blocked; local branch is ahead of upstream"
    if state.state == "diverged":
        return "blocked; local branch has diverged from upstream"
    return state.state


def _format_cmd(cmd: list[str]) -> str:
    return " ".join(shlex_quote(part) for part in cmd)


def shlex_quote(value: str) -> str:
    if not value:
        return "''"
    safe = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_@%+=:,./-"
    if all(char in safe for char in value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _python_install_command(info: InstallInfo) -> list[str] | None:
    root = info.git.root
    if root is None:
        return None
    if not info.packaging.pyproject and not info.packaging.setup_py and not info.packaging.setup_cfg:
        return None
    if info.python.editable is True:
        return [sys.executable, "-m", "pip", "install", "-e", "."]
    if info.python.editable is False:
        return [sys.executable, "-m", "pip", "install", "."]
    if info.packaging.pyproject:
        return [sys.executable, "-m", "pip", "install", "-e", "."]
    return None


def _js_install_command(info: InstallInfo) -> list[str] | None:
    overlay = info.overlay
    if not overlay.directory or not overlay.package_json_exists:
        return None
    if overlay.package_manager == "not detected":
        return None
    return [overlay.package_manager, "install"]


def _print_command_failure(result: CommandResult, out: TextIO) -> None:
    print(f"Command failed: {_format_cmd(list(result.args))}", file=out)
    print(f"Exit code: {result.returncode}", file=out)
    if result.stdout.strip():
        print("stdout:", file=out)
        print(result.stdout.strip(), file=out)
    if result.stderr.strip():
        print("stderr:", file=out)
        print(result.stderr.strip(), file=out)


def _refresh_python_dependencies(info: InstallInfo, out: TextIO) -> DependencyResult:
    cmd = _python_install_command(info)
    if cmd is None:
        print("Python dependency refresh skipped: install style could not be determined safely.", file=out)
        print("Manual guidance: from the repo, run python -m pip install -e . for editable installs or python -m pip install . for normal installs.", file=out)
        return DependencyResult(ok=True, skipped=True)
    print(f"Running: {_format_cmd(cmd)}", file=out)
    result = _run_command(cmd, cwd=info.git.root)
    if result.returncode != 0:
        print("Python dependency refresh failed.", file=out)
        _print_command_failure(result, out)
        return DependencyResult(ok=False)
    print("Python dependency refresh complete.", file=out)
    return DependencyResult(ok=True)


def _refresh_js_dependencies(info: InstallInfo, out: TextIO) -> DependencyResult:
    cmd = _js_install_command(info)
    overlay_dir = info.overlay.directory
    if cmd is None or overlay_dir is None:
        print("Electron overlay dependency refresh skipped: no overlay package.json was found.", file=out)
        return DependencyResult(ok=True, skipped=True)
    if not info.overlay.package_manager_available:
        print(f"Electron overlay dependency refresh skipped: {info.overlay.package_manager} is not available on PATH.", file=out)
        print(f"Manual guidance: install {info.overlay.package_manager}, then run {_format_cmd(cmd)} in {overlay_dir}.", file=out)
        return DependencyResult(ok=False, skipped=True)
    print(f"Running in {overlay_dir}: {_format_cmd(cmd)}", file=out)
    result = _run_command(cmd, cwd=overlay_dir)
    if result.returncode != 0:
        print("Electron overlay dependency refresh failed.", file=out)
        _print_command_failure(result, out)
        return DependencyResult(ok=False)
    print("Electron overlay dependency refresh complete.", file=out)
    return DependencyResult(ok=True)


def _skip_dependencies(info: InstallInfo, out: TextIO) -> DependencyResult:
    print("Skipped Python dependency refresh because --no-install was passed.", file=out)
    py_cmd = _python_install_command(info)
    if py_cmd:
        print(f"Manual Python command: {_format_cmd(py_cmd)}", file=out)
    else:
        print("Manual Python command: inspect install mode first; python -m pip install -e . may be appropriate for editable repo installs.", file=out)
    print("Skipped JS dependency refresh because --no-install was passed.", file=out)
    js_cmd = _js_install_command(info)
    if js_cmd and info.overlay.directory:
        print(f"Manual JS command: cd {info.overlay.directory} && {_format_cmd(js_cmd)}", file=out)
    else:
        print("Manual JS command: no overlay package.json was detected.", file=out)
    return DependencyResult(ok=True, skipped=True)


def _refresh_dependencies(info: InstallInfo, options: UpdateOptions, out: TextIO) -> bool:
    _print_section("Dependency Refresh", out)
    if options.no_install:
        return _skip_dependencies(info, out).ok
    py_result = _refresh_python_dependencies(info, out)
    js_result = _refresh_js_dependencies(info, out)
    return py_result.ok and js_result.ok


def _validation_commands() -> list[list[str]]:
    hermes_pet = shutil.which("hermes-pet")
    if hermes_pet:
        return [[hermes_pet, "--version"]]
    return [[sys.executable, "-m", "hermes_pet.cli", "--version"]]


def _run_validation(info: InstallInfo, out: TextIO) -> bool:
    _print_section("Validation", out)
    ok = True
    for cmd in _validation_commands():
        print(f"Running: {_format_cmd(cmd)}", file=out)
        result = _run_command(cmd, cwd=info.git.root)
        if result.returncode != 0:
            ok = False
            print("Validation failed.", file=out)
            _print_command_failure(result, out)
        elif result.stdout.strip():
            print(result.stdout.strip(), file=out)
    print(f"Doctor command detected but not run here because update must never modify {STATE_DIR_GUIDANCE}.", file=out)
    return ok


def _print_recovery_notes(out: TextIO) -> None:
    _print_section("Recovery Notes", out)
    print(f"- Back up the actual {STATE_DIR_GUIDANCE} directory before risky manual recovery.", file=out)
    print("- This command never auto-stashes, hard-resets, rebases, or creates merge commits.", file=out)
    print("- If dependency refresh failed, rerun the printed install command after fixing the reported tool issue.", file=out)
    print("- If git fast-forward failed, inspect git status and git log before deciding how to recover.", file=out)


def _confirm(options: UpdateOptions, out: TextIO, stdin: TextIO | None) -> bool:
    if options.yes:
        return True
    input_stream = stdin or sys.stdin
    if not (input_stream.isatty() and sys.stdout.isatty()):
        print("Non-interactive update requires --yes before mutating files.", file=out)
        return False
    answer = input("Proceed with the fast-forward update and dependency refresh? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def _block_dirty(info: InstallInfo, out: TextIO, *, check: bool) -> int:
    print("The working tree has uncommitted changes. Automatic update is blocked.", file=out)
    print("Commit, stash, or discard those changes first. This command will not auto-stash.", file=out)
    if check:
        print("--check completed; a normal update would be blocked.", file=out)
        return 0
    return 1


def _handle_no_upstream(out: TextIO, *, check: bool) -> int:
    print("No upstream branch is configured for this checkout.", file=out)
    print("Automatic update needs an upstream branch so it can compare and fast-forward safely.", file=out)
    print("Manual guidance: configure an upstream branch, for example git branch --set-upstream-to=origin/main.", file=out)
    return 0 if check else 1


def _handle_non_git(info: InstallInfo, options: UpdateOptions, out: TextIO) -> int:
    _print_update_plan(info, options, out)
    _print_section("Result", out)
    _manual_guidance(info, out)
    return 0 if options.check or options.dry_run else 1


def _run_check(info: InstallInfo, out: TextIO) -> int:
    _print_section("Actions Taken", out)
    if info.git.root is None:
        print("No git checkout was detected; no project files were changed.", file=out)
        return 0
    if info.git.upstream == "not configured":
        _print_section("Result", out)
        return _handle_no_upstream(out, check=True)
    if not _fetch(info.git.root, out):
        return 1
    state = _compare_upstream(info.git.root, info.git.upstream)
    _print_upstream_state(state, out)
    if info.git.dirty:
        _print_section("Result", out)
        return _block_dirty(info, out, check=True)
    _print_section("Result", out)
    print(f"Check result: {_check_result_line(state)}.", file=out)
    return 0 if state is not None else 1


def _run_dry_run(info: InstallInfo, options: UpdateOptions, out: TextIO) -> int:
    _print_update_plan(info, options, out)
    _print_section("Result", out)
    print("Dry run complete. No files were changed, no fetch was run, and no dependencies were installed.", file=out)
    if info.git.dirty:
        print("A normal update would be blocked by the dirty working tree shown above.", file=out)
    return 0


def _run_update(info: InstallInfo, options: UpdateOptions, out: TextIO, stdin: TextIO | None) -> int:
    if info.git.root is None:
        return _handle_non_git(info, options, out)
    if info.git.dirty:
        _print_section("Result", out)
        return _block_dirty(info, out, check=False)
    if info.git.upstream == "not configured":
        _print_section("Result", out)
        return _handle_no_upstream(out, check=False)

    _print_update_plan(info, options, out)
    _print_section("Actions Taken", out)
    if not _fetch(info.git.root, out):
        _print_recovery_notes(out)
        return 1

    state = _compare_upstream(info.git.root, info.git.upstream)
    _print_upstream_state(state, out)
    if state is None:
        _print_recovery_notes(out)
        return 1
    if state.state == "current":
        _print_section("Result", out)
        print("Already current. No update was needed.", file=out)
        return 0
    if state.state == "ahead":
        _print_section("Result", out)
        print("Local branch is ahead of upstream. Refusing to update blindly.", file=out)
        print("Push or otherwise reconcile local commits before running update again.", file=out)
        return 1
    if state.state == "diverged":
        _print_section("Result", out)
        print("Local branch has diverged from upstream. Refusing to merge, rebase, reset, or stash automatically.", file=out)
        print("Inspect git log --oneline --graph --decorate --all before choosing a manual recovery path.", file=out)
        return 1

    if not _confirm(options, out, stdin):
        _print_section("Result", out)
        print("Update was not started. Re-run with --yes in non-interactive automation.", file=out)
        return 1

    merge_result = _git(info.git.root, "merge", "--ff-only", info.git.upstream)
    if merge_result.returncode != 0:
        print("Fast-forward update failed.", file=out)
        _print_command_failure(merge_result, out)
        _print_recovery_notes(out)
        return 1
    print("Fast-forward update complete.", file=out)

    refreshed_info = collect_install_info(info.python.package_location)
    dependencies_ok = _refresh_dependencies(refreshed_info, options, out)
    validation_ok = _run_validation(refreshed_info, out)

    _print_section("Result", out)
    if dependencies_ok and validation_ok:
        print("Update completed successfully.", file=out)
        return 0
    print("Update completed, but one or more follow-up checks failed.", file=out)
    _print_recovery_notes(out)
    return 1


def _options_from_args(args: argparse.Namespace) -> UpdateOptions:
    return UpdateOptions(
        check=bool(getattr(args, "check", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
        yes=bool(getattr(args, "yes", False)),
        no_install=bool(getattr(args, "no_install", False)),
        verbose=bool(getattr(args, "verbose", False)),
    )


def run_update(
    args: argparse.Namespace,
    *,
    package_dir: Path | None = None,
    stdout: TextIO | None = None,
    stdin: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    options = _options_from_args(args)
    info = collect_install_info(package_dir)
    _print_preflight(info, out, verbose=options.verbose)

    if not info.automatic_update_available:
        return _handle_non_git(info, options, out)
    if options.dry_run:
        return _run_dry_run(info, options, out)
    if options.check:
        return _run_check(info, out)
    return _run_update(info, options, out, stdin)


def build_update_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--check", action="store_true", help="Inspect update availability without pulling or installing.")
    parser.add_argument("--dry-run", action="store_true", help="Print the update plan without fetching, pulling, or installing.")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip interactive confirmation for a safe mutating update.")
    parser.add_argument("--no-install", action="store_true", help="Skip Python and Electron overlay dependency refresh.")
    parser.add_argument("--verbose", action="store_true", help="Print extra diagnostics when available.")
