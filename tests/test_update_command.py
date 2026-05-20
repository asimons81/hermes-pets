from __future__ import annotations

import argparse
import io
import subprocess
from pathlib import Path

import pytest

from hermes_pet import cli, update


def _args(
    *,
    check: bool = False,
    dry_run: bool = False,
    yes: bool = False,
    no_install: bool = False,
    verbose: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(check=check, dry_run=dry_run, yes=yes, no_install=no_install, verbose=verbose)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def _write_project_files(repo: Path) -> Path:
    package_dir = repo / "src" / "hermes_pet"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        "\n".join(
            [
                "[build-system]",
                'requires = ["setuptools>=69", "wheel"]',
                'build-backend = "setuptools.build_meta"',
                "",
                "[project]",
                'name = "hermes-pet"',
                'version = "0.5.0"',
            ]
        ),
        encoding="utf-8",
    )
    overlay = repo / "overlay"
    overlay.mkdir()
    (overlay / "package.json").write_text('{"private": true}\n', encoding="utf-8")
    return package_dir


def _commit(repo: Path, path: str, text: str, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _repo_with_origin(tmp_path: Path) -> tuple[Path, Path, Path]:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "--initial-branch=main", str(origin))
    repo = tmp_path / "repo"
    _git(tmp_path, "clone", str(origin), str(repo))
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    package_dir = _write_project_files(repo)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "push", "-u", "origin", "main")
    return repo, package_dir, origin


def _push_remote_commit(tmp_path: Path, origin: Path, path: str = "remote.txt") -> str:
    other = tmp_path / f"other-{path.replace('/', '-')}"
    _git(tmp_path, "clone", str(origin), str(other))
    _git(other, "config", "user.email", "test@example.com")
    _git(other, "config", "user.name", "Test User")
    commit = _commit(other, path, "remote change\n", f"remote change {path}")
    _git(other, "push", "origin", "main")
    return commit


def _run(args: argparse.Namespace, package_dir: Path) -> tuple[int, str]:
    out = io.StringIO()
    code = update.run_update(args, package_dir=package_dir, stdout=out)
    return code, out.getvalue()


def _fake_install_info(
    *,
    mode: str,
    automatic: bool,
    package_location: Path,
    editable: bool | None = None,
    source_url: str = "",
    overlay: update.OverlayInfo | None = None,
) -> update.InstallInfo:
    return update.InstallInfo(
        python=update.PythonInstallInfo("0.3.0", package_location, package_location.parent, editable, source_url),
        git=update.GitInfo(None, "not detected", "not detected", "not detected", "not detected", False, ()),
        overlay=overlay or update.OverlayInfo(None, False, "none", False, "not detected", False),
        packaging=update.PackagingInfo(False, False, False),
        detected_mode=mode,
        automatic_update_available=automatic,
    )


def test_check_fetches_metadata_without_merging_or_installing(tmp_path: Path) -> None:
    repo, package_dir, origin = _repo_with_origin(tmp_path)
    starting_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _push_remote_commit(tmp_path, origin)

    code, output = _run(_args(check=True), package_dir)

    assert code == 0
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == starting_head
    assert not (repo / "remote.txt").exists()
    assert "Repository state: behind" in output
    assert "Check result: update available" in output
    assert "Dependency Refresh" not in output


def test_check_reports_current_repo_without_mutating(tmp_path: Path) -> None:
    repo, package_dir, _origin = _repo_with_origin(tmp_path)
    starting_head = _git(repo, "rev-parse", "HEAD").stdout.strip()

    code, output = _run(_args(check=True), package_dir)

    assert code == 0
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == starting_head
    assert "Repository state: current" in output
    assert "Commits ahead: 0" in output
    assert "Commits behind: 0" in output
    assert "Check result: current; no update is available." in output


def test_check_dirty_tree_reports_block_but_exits_successfully(tmp_path: Path) -> None:
    repo, package_dir, origin = _repo_with_origin(tmp_path)
    _push_remote_commit(tmp_path, origin)
    (repo / "README.md").write_text("local edit\n", encoding="utf-8")

    code, output = _run(_args(check=True), package_dir)

    assert code == 0
    assert "Dirty working tree: yes" in output
    assert "README.md" in output
    assert "--check completed; a normal update would be blocked." in output
    assert not (repo / "remote.txt").exists()


def test_dry_run_does_not_fetch_merge_or_install(tmp_path: Path) -> None:
    repo, package_dir, origin = _repo_with_origin(tmp_path)
    starting_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    starting_origin = _git(repo, "rev-parse", "origin/main").stdout.strip()
    _push_remote_commit(tmp_path, origin)

    code, output = _run(_args(dry_run=True), package_dir)

    assert code == 0
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == starting_head
    assert _git(repo, "rev-parse", "origin/main").stdout.strip() == starting_origin
    assert "Dry run complete" in output
    assert "No files were changed, no fetch was run, and no dependencies were installed." in output


def test_dirty_git_tree_blocks_update_and_lists_changed_files(tmp_path: Path) -> None:
    repo, package_dir, origin = _repo_with_origin(tmp_path)
    _push_remote_commit(tmp_path, origin)
    (repo / "README.md").write_text("local edit\n", encoding="utf-8")

    code, output = _run(_args(yes=True, no_install=True), package_dir)

    assert code == 1
    assert "Dirty working tree: yes" in output
    assert "README.md" in output
    assert "Automatic update is blocked" in output
    assert not (repo / "remote.txt").exists()


def test_clean_git_tree_can_fast_forward_with_no_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, package_dir, origin = _repo_with_origin(tmp_path)
    remote_commit = _push_remote_commit(tmp_path, origin)
    monkeypatch.setattr(update, "_run_validation", lambda info, out: True)

    code, output = _run(_args(yes=True, no_install=True), package_dir)

    assert code == 0
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == remote_commit
    assert (repo / "remote.txt").read_text(encoding="utf-8") == "remote change\n"
    assert "Fast-forward update complete." in output
    assert "Skipped Python dependency refresh because --no-install was passed." in output
    assert "Skipped JS dependency refresh because --no-install was passed." in output


def test_no_upstream_branch_produces_safe_failure(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    package_dir = _write_project_files(repo)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    code, output = _run(_args(yes=True), package_dir)

    assert code == 1
    assert "No upstream branch is configured" in output
    assert "git branch --set-upstream-to=origin/main" in output


def test_branch_ahead_blocks_blind_update(tmp_path: Path) -> None:
    repo, package_dir, _origin = _repo_with_origin(tmp_path)
    _commit(repo, "local.txt", "local change\n", "local change")

    code, output = _run(_args(yes=True, no_install=True), package_dir)

    assert code == 1
    assert "Repository state: ahead" in output
    assert "Refusing to update blindly" in output


def test_diverged_branch_blocks_update(tmp_path: Path) -> None:
    repo, package_dir, origin = _repo_with_origin(tmp_path)
    _commit(repo, "local.txt", "local change\n", "local change")
    _push_remote_commit(tmp_path, origin)

    code, output = _run(_args(yes=True, no_install=True), package_dir)

    assert code == 1
    assert "Repository state: diverged" in output
    assert "Refusing to merge, rebase, reset, or stash automatically" in output


def test_non_interactive_update_without_yes_does_not_mutate(tmp_path: Path) -> None:
    repo, package_dir, origin = _repo_with_origin(tmp_path)
    starting_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _push_remote_commit(tmp_path, origin)

    code, output = _run(_args(no_install=True), package_dir)

    assert code == 1
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == starting_head
    assert "Non-interactive update requires --yes" in output
    assert not (repo / "remote.txt").exists()


@pytest.mark.parametrize(
    ("lockfile", "expected_manager"),
    [
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("package-lock.json", "npm"),
        ("", "npm"),
    ],
)
def test_lockfile_selection_chooses_package_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lockfile: str,
    expected_manager: str,
) -> None:
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "package.json").write_text("{}", encoding="utf-8")
    if lockfile:
        (overlay / lockfile).write_text("", encoding="utf-8")
    monkeypatch.setattr(update.shutil, "which", lambda command: f"/usr/bin/{command}")

    manager, detected_lockfile, available = update.select_package_manager(overlay)

    assert manager == expected_manager
    assert detected_lockfile == (lockfile or "none")
    assert available is True


def test_missing_package_manager_reports_warning(tmp_path: Path) -> None:
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "package.json").write_text("{}", encoding="utf-8")
    info = update.InstallInfo(
        python=update.PythonInstallInfo("0.3.0", tmp_path, None, None, ""),
        git=update.GitInfo(tmp_path, "main", "abc", "origin", "origin/main", False, ()),
        overlay=update.OverlayInfo(overlay, True, "pnpm-lock.yaml", False, "pnpm", False),
        packaging=update.PackagingInfo(True, False, False),
        detected_mode="git checkout",
        automatic_update_available=True,
    )
    out = io.StringIO()

    result = update._refresh_js_dependencies(info, out)

    assert result.ok is False
    assert "pnpm is not available on PATH" in out.getvalue()


def test_unknown_install_mode_returns_useful_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_dir = tmp_path / "site-packages" / "hermes_pet"
    package_dir.mkdir(parents=True)

    def missing_distribution(*args, **kwargs):
        raise update.metadata.PackageNotFoundError

    monkeypatch.setattr(update.metadata, "version", missing_distribution)
    monkeypatch.setattr(update.metadata, "distribution", missing_distribution)

    code, output = _run(_args(), package_dir)

    assert code == 1
    assert "unknown install mode" in output
    assert "Automatic update is unavailable" in output
    assert "Suggested manual paths" in output


def test_normal_package_install_reports_source_and_no_automatic_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_dir = tmp_path / "site-packages" / "hermes_pet"
    package_dir.mkdir(parents=True)
    info = _fake_install_info(
        mode="normal Python package; Electron overlay dependencies present",
        automatic=False,
        package_location=package_dir,
        editable=False,
        source_url="git+https://github.com/asimons81/hermes-pets.git",
        overlay=update.OverlayInfo(package_dir / "overlay", True, "none", True, "npm", True),
    )
    monkeypatch.setattr(update, "collect_install_info", lambda package_dir=None: info)
    out = io.StringIO()

    code = update.run_update(_args(check=True), package_dir=package_dir, stdout=out)
    output = out.getvalue()

    assert code == 0
    assert "Detected install mode: normal Python package; Electron overlay dependencies present" in output
    assert "Automatic update: unavailable for this install mode" in output
    assert "Package source: git+https://github.com/asimons81/hermes-pets.git" in output
    assert "Recorded package source: git+https://github.com/asimons81/hermes-pets.git" in output


def test_normal_package_inside_checkout_does_not_enable_git_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _source_package_dir, _origin = _repo_with_origin(tmp_path)
    site_packages = repo / ".venv" / "lib" / "python3.11" / "site-packages"
    installed_package_dir = site_packages / "hermes_pet"
    installed_package_dir.mkdir(parents=True)
    (installed_package_dir / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(update, "_distribution_info", lambda package_location: (site_packages, False, ""))

    info = update.collect_install_info(installed_package_dir)

    assert info.git.root is None
    assert info.automatic_update_available is False
    assert "normal Python package" in info.detected_mode


def test_overlay_dependency_diagnostics_report_present_and_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    package_dir = _write_project_files(repo)

    missing = update._collect_overlay_info(repo, package_dir)
    assert missing.package_json_exists is True
    assert missing.node_modules_exists is False

    (repo / "overlay" / "node_modules").mkdir()
    present = update._collect_overlay_info(repo, package_dir)
    assert present.package_json_exists is True
    assert present.node_modules_exists is True


def test_update_logic_never_touches_default_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, package_dir, _origin = _repo_with_origin(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    code, output = _run(_args(check=True, verbose=True), package_dir)

    assert code == 0
    assert "State directory inspection: skipped by update; ~/.hermes_pet is never touched" in output
    assert "Doctor command" not in output
    assert not (home / ".hermes_pet").exists()
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""


def test_cli_update_entrypoint_wires_parser_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    def fake_run_update(args):
        seen["check"] = args.check
        seen["dry_run"] = args.dry_run
        seen["yes"] = args.yes
        seen["no_install"] = args.no_install
        seen["verbose"] = args.verbose
        return 23

    monkeypatch.setattr(cli, "run_update", fake_run_update)

    assert cli.main(["update", "--check", "--dry-run", "--yes", "--no-install", "--verbose"]) == 23
    assert seen == {
        "check": True,
        "dry_run": True,
        "yes": True,
        "no_install": True,
        "verbose": True,
    }


def test_stale_editable_metadata_prefers_pyproject_source_truth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the installed distribution metadata is stale (e.g. 0.1.0) but the
    checkout pyproject.toml is newer (e.g. 0.5.0), current_version() must
    return the source truth, not the stale metadata."""
    repo = tmp_path / "repo"
    package_dir = _write_project_files(repo)

    def stale_metadata_version(name: str) -> str:
        return "0.1.0"

    monkeypatch.setattr(update.metadata, "version", stale_metadata_version)

    version = update.current_version(package_dir)
    assert version == "0.5.0", f"expected source truth 0.5.0, got stale metadata {version}"


def test_current_version_falls_back_to_metadata_when_no_pyproject(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When there is no pyproject.toml near the package, current_version()
    falls back to importlib.metadata.version."""
    package_dir = tmp_path / "no_pyproject_here"
    package_dir.mkdir()

    def fake_metadata_version(name: str) -> str:
        return "0.5.0"

    monkeypatch.setattr(update.metadata, "version", fake_metadata_version)
    # Ensure CWD has no pyproject.toml so the candidate scan falls through.
    monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)

    version = update.current_version(package_dir)
    assert version == "0.5.0"


def test_python_environment_hint_prefers_executable_venv_over_inherited_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_venv = tmp_path / "project" / ".venv"
    executable = project_venv / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    (project_venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    inherited = tmp_path / "wrong-hermes-venv"
    monkeypatch.setenv("VIRTUAL_ENV", str(inherited))

    hint = update._python_environment_hint(executable)

    assert f"virtual environment ({project_venv.resolve()})" in hint
    assert f"inherited VIRTUAL_ENV differs ({inherited})" in hint


def test_python_environment_hint_reports_matching_project_venv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_venv = tmp_path / "project" / ".venv"
    executable = project_venv / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    (project_venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    monkeypatch.setenv("VIRTUAL_ENV", str(project_venv))

    assert update._python_environment_hint(executable) == f"virtual environment ({project_venv.resolve()})"


def test_python_environment_hint_reports_uv_tool_with_inherited_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / ".local" / "share" / "uv" / "tools" / "hermes-pet" / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    inherited = tmp_path / "wrong-env"
    monkeypatch.setenv("VIRTUAL_ENV", str(inherited))

    hint = update._python_environment_hint(executable)

    assert hint.startswith("uv tool environment")
    assert f"inherited VIRTUAL_ENV differs ({inherited})" in hint


def test_python_environment_hint_reports_standalone_executable_and_inherited_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    inherited = tmp_path / "ambient-env"
    monkeypatch.setenv("VIRTUAL_ENV", str(inherited))

    hint = update._python_environment_hint(executable)

    assert hint == f"system or unknown Python environment; inherited VIRTUAL_ENV set ({inherited})"
