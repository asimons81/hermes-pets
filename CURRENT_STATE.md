# Hermes Pets Current State

Snapshot date: 2026-05-05

## What Works

- Python CLI is installable as `hermes-pet` and `hermes-pet-bridge`.
- Pet state persists under `~/.hermes_pet` by default.
- `hermes-pet launch` starts the bridge and launches the Electron overlay.
- `hermes-pet launch --replace` stops existing Windows overlay process trees before starting a fresh overlay.
- Overlay movement, saved position, visible sprite bounds, and reconnect behavior are in place.
- Ambient events can be emitted with `hermes-pet emit`.
- Local commands can be wrapped with `wrap` or `run`.
- Wrapped-job history records success/failure, duration, exit code, redacted command, and short summaries.
- `hermes-pet retry` reruns the latest safe failed wrapped command.
- `hermes-pet message` emits external message notifications with source, sender, urgency, and optional open-command metadata.
- Quiet, silent, mute, and preference controls exist.
- `hermes-pet brief` summarizes recent jobs and events.
- Animated custom pets can be validated, imported into `~/.hermes_pet/custom-pets`, selected, listed, and removed with `hermes-pet custom-pet ...`.
- The bridge sends selected custom pet metadata to the overlay, and the renderer can load custom package frames from the local custom pet path.
- A repo-local Codex skill exists at `.codex/skills/hermes-pet-hatch/SKILL.md` for creating Hermes-compatible custom pet packages.
- `hermes-pet doctor` checks CLI, bridge, overlay, state, prefs, and job history.
- Bash helpers and a smoke script are available for daily operation.

## Key Commands

```bash
pip install -e .
uv tool install --editable /home/tony/projects/hermes-pet
hermes-pet
hermes-pet status
hermes-pet custom-pet list
hermes-pet custom-pet validate <path>
hermes-pet custom-pet import <path> --name <name>
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
hermes-pet prefs
hermes-pet brief --since 24h
hermes-pet brief --emit
hermes-pet doctor
scripts/smoke-hermes-pet.sh
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
- `scripts/validate-custom-pet.py`: custom pet package validator.
- `scripts/package-custom-pet.py`: custom pet package helper for hatch runs and built-in fixtures.
- `.codex/skills/hermes-pet-hatch/SKILL.md`: Hermes-specific custom pet creation workflow.
- `CUSTOM_PETS.md`: custom pet package format and CLI docs.

## Known Limitations

- The overlay is primarily tuned for WSL launching a Windows Electron window.
- Editable installs use the repo-local `overlay/`; non-editable installs use packaged overlay assets cached under `~/.hermes_pet/cache/overlay`.
- The bridge must be reachable for live overlay events; local event/job history still records when the bridge is unavailable.
- Custom pet `idle` is required; missing optional states rely on renderer fallback behavior.
- Custom pet selection is local state only and does not add the pet to built-in gacha species metadata.
- `doctor` returns success even with warnings, so read the warning lines rather than relying only on the exit code.
- `retry` only targets the latest failed job and refuses redacted sensitive commands.
- The smoke script intentionally creates one successful job and one expected failed job in local history.
- `emit`, `message`, and `brief --emit` require the bridge/overlay to be running.

## Next Recommended Improvements

- Add a lightweight automated test suite for CLI command behavior, job history, preference normalization, and event schema validation.
- Add a non-mutating smoke mode that uses a temporary `HERMES_PET_HOME`.
- Make `doctor` optionally return non-zero for CI-style strict checks.
- Add a compact cleanup/export command for state, prefs, event history, and jobs.
- Add richer renderer tests or browser-level overlay smoke checks for sprite visibility and event reactions.
- Add a visual package preview command for custom pets.
- Document a regular backup path for `~/.hermes_pet`.
