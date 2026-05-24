# Hermes Pets Demo Plan

Use this as the capture checklist for the first private repo post and demo.

## Screenshots and GIFs

- First launch: pet overlay appearing after `hermes-pet launch`.
- Bubble event: `hermes-pet emit bubble "Starting work"` with the overlay visible.
- Wrapped success: command starts, runs, and finishes with a positive reaction.
- Wrapped failure: expected failing command produces a failure reaction and appears in job history.
- Job history: terminal output from `hermes-pet jobs --last`.
- Brief: terminal output from `hermes-pet brief --since 24h`.
- Custom pet: `hermes-pet custom-pet current` plus the overlay using a custom or built-in animated pet.
- Doctor: a clean or understandable `hermes-pet doctor` run showing the WSL/Windows bridge and overlay checks.
- State diagnostics: `hermes-pet state export --since 24h` described as a redacted support snapshot, not a backup.
- Backup confidence: a terminal showing the active `HERMES_PET_HOME` path and the backup directory copy command, without showing private state contents.

## Demo Commands

```bash
cd <repo>
hermes-pet doctor
hermes-pet launch --replace
hermes-pet emit bubble "Starting the Hermes Pets demo"
hermes-pet wrap --name "Demo success" -- bash -lc 'sleep 1; echo done'
hermes-pet wrap --name "Demo expected failure" -- bash -lc 'sleep 1; exit 2'
hermes-pet jobs --last
hermes-pet jobs --failed --last
hermes-pet brief --since 24h
hermes-pet custom-pet list
hermes-pet overlay-status
hermes-pet state export --since 24h --output /tmp/hermes-pet-demo-state.json
```

Use `state export` only for diagnostics during the demo. For backup/restore
coverage, narrate the directory copy workflow from `README.md` or
`OPERATOR_GUIDE.md` instead of presenting the export JSON as restorable state.

## Live Verification Notes

Capture at least one live overlay shot in addition to command output. The live
overlay proves the WSL bridge, Windows Electron process, visible sprite, tray,
and attention states are working together. Renderer/package smokes are useful
supporting evidence, but they are not a replacement for the visible overlay
capture.

For custom pets, use a temporary preview state when possible:

```bash
preview_home="$(mktemp -d)"
HERMES_PET_HOME="$preview_home" hermes-pet custom-pet import docs/fixtures/custom-pets/minimal-spark --name minimal-spark
HERMES_PET_HOME="$preview_home" hermes-pet custom-pet use minimal-spark
HERMES_PET_HOME="$preview_home" hermes-pet launch --replace
```

Record the contact sheet if using a generated package, then record the live
overlay after selection so the demo shows both package inspection and real load.

## Short Launch Script

```bash
#!/usr/bin/env bash
set -euo pipefail

cd <repo>
hermes-pet doctor
hermes-pet launch --replace
hermes-pet emit bubble "Hermes Pets is live"
hermes-pet wrap --name "Demo smoke" -- bash -lc 'sleep 1; echo smoke-ok'
hermes-pet brief --since 24h
```

## First Post

- Lead with the actual thing: a local animated desktop pet for WSL/Windows coding sessions.
- Say why it exists: visible, local feedback for jobs, messages, quiet mode, failures, and daily context.
- Show the quickstart: `pip install -e .`, `hermes-pet launch`, and one `emit` or `wrap` command.
- Mention custom pets: generated packages live under `~/.hermes_pet/custom-pets`, not in the repo.
- Mention state handling carefully: `HERMES_PET_HOME` is the restorable state root; `state export` is redacted diagnostics.
- Call out current scope honestly: private first push, local-first, WSL/Windows tuned, no hosted service.
- Include one GIF of launch plus event reactions, one terminal screenshot of `jobs --last` or `brief`, and one still of a custom pet.
