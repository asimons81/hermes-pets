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

## Demo Commands

```bash
cd /home/tony/projects/hermes-pet
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
```

## Short Launch Script

```bash
#!/usr/bin/env bash
set -euo pipefail

cd /home/tony/projects/hermes-pet
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
- Call out current scope honestly: private first push, local-first, WSL/Windows tuned, no hosted service.
- Include one GIF of launch plus event reactions, one terminal screenshot of `jobs --last` or `brief`, and one still of a custom pet.
