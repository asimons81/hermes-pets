# Hermes Pets

![Hermes Pets promo banner](docs/assets/hermes-pet-banner-updated.png)

Hermes Pets is a local desktop companion for Hermes-style daily work, a small overlay that reacts to commands, messages, briefs, and ambient status events while staying fully controllable from the terminal.

It exists to make long local coding sessions feel more legible and alive. The pet gives visible feedback when work starts, finishes, fails, needs attention, or goes quiet, without requiring a hosted service or remote account.

## Start here

If you only want the map, read [`docs/README.md`](docs/README.md).

If you want day-to-day use, open:
- [`OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) for the short daily operator flow
- [`CURRENT_STATE.md`](CURRENT_STATE.md) for the current snapshot of what works
- [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) for release prep and verification
- [`CUSTOM_PETS.md`](CUSTOM_PETS.md) and [`docs/custom-pets/README.md`](docs/custom-pets/README.md) for custom pet packages and the curated gallery
- [`docs/releases/`](docs/releases/) and [`release-readiness/`](release-readiness/) for shipped and historical release notes

## Quickstart

Install from GitHub:

```bash
pip install 'git+https://github.com/asimons81/hermes-pets.git'
```

Or, for local development:

```bash
cd <repo>
pip install -e .
```

Then launch the bridge and overlay:

```bash
hermes-pet launch
hermes-pet emit bubble "Hello from Hermes Pets"
hermes-pet doctor
hermes-pet dashboard --no-open
```

On WSL and Windows, run the CLI from WSL. `hermes-pet launch` starts the Python bridge in WSL and opens the Electron overlay through the Windows launcher.

## Core commands

```bash
hermes-pet launch
hermes-pet launch --replace
hermes-pet overlay-status
hermes-pet emit bubble "Starting work"
hermes-pet wrap --name "Tests" -- pytest
hermes-pet jobs --last
hermes-pet brief --since 24h
hermes-pet quiet
hermes-pet mute 30m
hermes-pet doctor
hermes-pet doctor --strict
hermes-pet dashboard --no-open
```

## What the tool does

- Launch one floating pet overlay from WSL and Windows.
- Emit lightweight activity events to the overlay.
- Wrap commands so success, failure, duration, and retry info get recorded.
- Send message notifications from external channels.
- Control quiet and mute preferences for bubbles.
- Generate a short local brief from recent jobs and events.
- Open a localhost-only, token-protected dashboard for state, custom pets, prefs, voice preview, and achievements.
- Diagnose bridge, overlay, state, prefs, and job-history health.

## Platform support

WSL2 on Windows 10/11 with Windows interop is the supported platform for the full CLI, bridge, and floating Electron overlay experience. Native Linux, macOS, and native Windows are investigation targets only in Phase 5, so do not treat CLI-only behavior on those platforms as full overlay support.

See [`docs/platform-support.md`](docs/platform-support.md) for the supported platform matrix and known blockers.

## Updating Hermes Pets

Use the guarded update command when you want Hermes Pets to inspect or update itself without remembering the git, Python packaging, and Electron overlay steps by hand:

```bash
hermes-pet update --check
hermes-pet update --dry-run
hermes-pet update
hermes-pet update --yes
hermes-pet update --no-install
hermes-pet update --verbose
```

## Need more detail?

Read the docs map first: [`docs/README.md`](docs/README.md).
