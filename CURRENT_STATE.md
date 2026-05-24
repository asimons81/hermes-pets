# Hermes Pets Current State

Snapshot date: 2026-05-24

## What Works

- Python CLI is installable as `hermes-pet` and `hermes-pet-bridge`.
- Pet state persists under `~/.hermes_pet` by default.
- `hermes-pet launch` starts the bridge and launches the Electron overlay.
- `hermes-pet launch --replace` stops existing Windows overlay process trees before starting a fresh overlay.
- On WSL/Windows, the launcher mirrors the overlay app into `%LOCALAPPDATA%\HermesAgent\pet-overlay-electron\app-<port>` so Electron reads renderer files from a native Windows path rather than a WSL UNC path.
- Overlay movement, saved position, visible sprite bounds, and reconnect behavior are in place.
- Ambient events can be emitted with `hermes-pet emit`.
- Local commands can be wrapped with `wrap` or `run`.
- Wrapped-job history records success/failure, duration, exit code, redacted command, and short summaries.
- `hermes-pet retry` reruns the latest safe failed wrapped command.
- `hermes-pet message` emits external message notifications with source, sender, urgency, and optional open-command metadata.
- Quiet, silent, mute, and preference controls exist.
- Named notification profiles exist for normal, focus, pairing, demo, and silent workflows.
- `hermes-pet dashboard` serves a polished localhost-only, token-protected dashboard on port `17474` by default.
- Dashboard APIs expose state snapshots, notification prefs, custom pet management, voice preview controls, achievements, and a test overlay event.
- Dashboard static assets are packaged with wheel/sdist artifacts and work from editable installs.
- v0.3.0 dashboard QA screenshots and evidence are recorded in `docs/assets/hermes-pets-dashboard-v030-overview.png` and `docs/dashboard-v030-qa.md`.
- Voice preview is opt-in only, off by default, adapter-command based, and bounded by an event allowlist.
- Foundational achievements persist in `achievements.json` and unlock idempotently for custom pets, jobs, retryable failures, and level milestones.
- `hermes-pet brief` summarizes recent jobs and events.
- `hermes-pet state export` produces compact redacted diagnostics, and `hermes-pet state cleanup` supports bounded local maintenance.
- Renderer smoke coverage checks startup, reconnect, event reactions, custom pet loading, and fallback behavior without launching Electron.
- Live overlay verification is documented separately because renderer/package smokes do not prove WSL-to-Windows launch, visible animation, tray grouping, or attention-state behavior in Electron.
- Animated custom pets can be validated, imported into `~/.hermes_pet/custom-pets`, selected, listed, and removed with `hermes-pet custom-pet ...`.
- The bridge sends selected custom pet metadata to the overlay, and the renderer can load custom package frames from the local custom pet path.
- Custom pet docs include temporary-state preview and minimal-template workflows.
- Community custom pet contribution docs and issue/PR checklists define curated submissions, validation evidence, preview evidence, and licensing expectations without a hosted gallery.
- Phase 5 release closeout docs define the 0.1.1 versus 0.2.0 decision mechanics; the explicit release task bumped the package version to 0.2.0.
- Phase 5 readiness passed on WSL/Windows on 2026-05-07: pytest, renderer smoke,
  package artifact verification, packaged overlay verification, temp-state CLI
  smoke, live overlay verification, and fresh install smoke against the current
  workspace target.
- v0.3.0 release readiness passed on WSL/Windows on 2026-05-08: compileall,
  pytest, JS syntax checks, renderer smoke, shell syntax checks, sprite manifest
  validation, temp-state and fresh-install CLI smokes, packaged overlay
  verification, wheel/sdist artifact inspection, live overlay verification,
  local install smoke, and `hermes-pet doctor`.
- A repo-local Codex skill exists at `.codex/skills/hermes-pet-hatch/SKILL.md` for creating Hermes-compatible custom pet packages.
- `hermes-pet doctor` checks CLI, bridge, overlay, state, prefs, and job history.
- `hermes-pet doctor --strict` returns non-zero when any doctor check warns.
- Bash helpers and a smoke script are available for daily operation.
- A temp-state smoke mode and a fresh GitHub install smoke script are available for release confidence.
- WSL2/Windows with Windows interop is the supported full-overlay platform; native Linux, macOS, and native Windows are documented as investigation targets only.
- v0.6.0 recap export release candidate is prepared as the shareability release: local recap card exports can be rendered, bundled, and validated end to end with temp-state evidence. It still needs Tony approval before push, tag, GitHub Release, PyPI, or installer work.

## Key Commands

```bash
pip install -e .
uv tool install --editable /home/tony/projects/hermes-pet
hermes-pet
hermes-pet status
hermes-pet custom-pet list
hermes-pet custom-pet validate <path>
hermes-pet custom-pet import <path> --name <name>
hermes-pet custom-pet codex
hermes-pet custom-pet import-codex latest --use
hermes-pet custom-pet preview --installed <name> --output /tmp/custom-pet-preview.html
hermes-pet custom-pet use <name>
hermes-pet custom-pet current
hermes-pet launch
hermes-pet launch --replace
hermes-pet overlay-status
hermes-pet emit bubble "Starting work"
hermes-pet wrap --name "API tests" -- pytest
hermes-pet run -- npm test
hermes-pet jobs
hermes-pet jobs --failed --last
hermes-pet retry
hermes-pet message --source telegram --sender "Ada" "Can you review this?"
hermes-pet quiet
hermes-pet quiet --silent
hermes-pet quiet --off
hermes-pet mute 30m
hermes-pet profile focus
hermes-pet prefs
hermes-pet dashboard --no-open
hermes-pet voice status
hermes-pet voice test "Hermes Pets voice preview test."
hermes-pet state export --since 24h
hermes-pet state cleanup --dry-run
hermes-pet brief --since 24h
hermes-pet brief --emit
hermes-pet doctor
hermes-pet doctor --strict
node scripts/smoke-renderer.js
scripts/smoke-hermes-pet.sh --temp-state
scripts/smoke-github-install.sh
```

Optional shell helpers:

```bash
source /home/tony/projects/hermes-pet/shell-helpers/hermes-pet.bash
hp
hpl
hps
hpjobs
hpfail
hpwrap "Job name" -- command arg...
hpbrief
```

## Important Files

- `README.md`: full daily-use and recovery documentation.
- `OPERATOR_GUIDE.md`: short operator guide.
- `pyproject.toml`: Python package metadata and CLI entry points.
- `src/hermes_pet/cli.py`: CLI commands, launch, doctor, jobs, retry, prefs, brief.
- `src/hermes_pet/bridge.py`: WebSocket bridge and event delivery.
- `src/hermes_pet/dashboard.py`: localhost dashboard server and API handlers.
- `src/hermes_pet/dashboard/`: packaged static dashboard UI.
- `src/hermes_pet/voice.py`: opt-in voice preview preferences and adapter execution.
- `src/hermes_pet/achievements.py`: foundational achievement definitions and state.
- `src/hermes_pet/custom_pets.py`: custom pet validation, import, selection, and bridge payload helpers.
- `src/hermes_pet/events.py`: normalized local event schema.
- `src/hermes_pet/event_log.py`: local event history.
- `src/hermes_pet/jobs.py`: job history, redaction, retry safety.
- `src/hermes_pet/prefs.py`: quiet/mute preference storage.
- `overlay/src/main.js`: Electron overlay runtime.
- `overlay/src/main.windows.js`: Windows entry point for the overlay.
- `overlay/src/renderer.js`: sprite rendering and event reactions.
- `overlay/src/preload.js`: safe renderer API exposure.
- `overlay/scripts/launch-windows-overlay.ps1`: Windows single-instance launcher.
- `shell-helpers/hermes-pet.bash`: Bash aliases/functions.
- `scripts/smoke-hermes-pet.sh`: smoke verification script.
- `scripts/smoke-renderer.js`: dependency-free renderer behavior smoke check.
- `scripts/smoke-github-install.sh`: fresh virtualenv install smoke for the public GitHub install path.
- `scripts/verify-live-overlay.sh`: WSL/Windows live Electron overlay verifier with bounded retry for transient Electron startup/teardown races.
- `scripts/validate-custom-pet.py`: custom pet package validator.
- `scripts/package-custom-pet.py`: custom pet package helper for hatch runs and built-in fixtures.
- `.codex/skills/hermes-pet-hatch/SKILL.md`: Hermes-specific custom pet creation workflow.
- `CUSTOM_PETS.md`: custom pet package format and CLI docs.
- `docs/custom-pet-contributions.md`: community custom pet submission, validation, preview, licensing, and curation workflow.
- `docs/release-closeout.md`: Phase 5 verification evidence and next-version recommendation mechanics.
- `docs/dashboard-polish-audit.md`: v0.3.0 dashboard structure, API contract, and polish constraints.
- `docs/dashboard-v030-qa.md`: v0.3.0 dashboard screenshot and readiness evidence.
- `docs/platform-support.md`: supported platform matrix, CLI-only boundaries, and known platform blockers.

## Known Limitations

- The full overlay path is supported on WSL2/Windows with Windows interop. Native Linux, macOS, and native Windows are not supported full-overlay platforms in Phase 5.
- Editable installs use the repo-local `overlay/` as source; WSL/Windows launch mirrors the active overlay source into the Windows Electron cache before launch. Non-editable installs use packaged overlay assets cached under `~/.hermes_pet/cache/overlay` first.
- The bridge must be reachable for live overlay events; local event/job history still records when the bridge is unavailable.
- Custom pet `idle` is required; missing optional states rely on renderer fallback behavior.
- Custom pet selection is local state only and does not add the pet to built-in gacha species metadata.
- Backups must copy `${HERMES_PET_HOME:-~/.hermes_pet}` directly; state export is redacted diagnostics and is not restorable backup data.
- `doctor` returns success even with warnings by default, so read the warning lines for daily use; use `doctor --strict` for CI-style failure on warnings.
- `retry` only targets the latest failed job and refuses redacted sensitive commands.
- The smoke script intentionally creates one successful job and one expected failed job in the active state directory; use `--temp-state` to isolate that history.
- `emit`, `message`, and `brief --emit` require the bridge/overlay to be running.
- The dashboard is localhost-only and token-protected. It is not a hosted or remote UI.
- Voice mode is preview plumbing only; no provider selection or always-on personality mode is included.
- Achievements are a compact state foundation only; no rich celebration system is included.

## Next Recommended Improvements

- Await Tony's explicit release approval, then push the prepared commits, create/tag `v0.6.0`, and draft the GitHub Release. Do not publish to PyPI or build an installer unless separately approved.
- Keep PR #71 / macOS work out of the v0.6.0 release train; native platform expansion is still a later investigation target.
- Add deeper live overlay checks for drag ergonomics, always-on-top behavior, and multi-monitor/DPI setups.
- Add richer custom pet preview controls such as playback speed and side-by-side state comparison.
- Add an automated backup helper around `${HERMES_PET_HOME:-~/.hermes_pet}` once the manual copy/restore workflow has enough field use.
