# Hermes Pets Operator Guide

This is the short version for daily use.

## Startup

Start the bridge and overlay:

```bash
hermes-pet launch
```

If you see duplicate overlays or the sprite looks stale, replace the overlay:

```bash
hermes-pet launch --replace
```

Check what is running:

```bash
hermes-pet overlay-status
hermes-pet doctor
hermes-pet doctor --strict
```

On WSL/Windows, run these commands from WSL. `launch` starts or reuses the
Python bridge in WSL, then calls the Windows PowerShell launcher at
`overlay/scripts/launch-windows-overlay.ps1`. That launcher keeps Electron
dependencies in `%LOCALAPPDATA%\HermesAgent\pet-overlay-electron` and opens the
floating Windows overlay against `ws://127.0.0.1:17473` unless the port or URL is
overridden.

For reliable launch checks, keep `/mnt/c/Windows/System32/WindowsPowerShell/v1.0`
and `/mnt/c/Windows/system32` on the WSL `PATH`. If `doctor`, `overlay-status`,
`launch`, or `close` cannot find the Windows launcher or process tools, fix the
WSL shell `PATH` first, then rerun `hermes-pet doctor`.

Close only the overlay:

```bash
hermes-pet close
```

Add `--bridge` only when you also want to stop the event bridge.

## Phase 2 Manual Live Overlay Verification

Use this checklist before calling Phase 2 overlay behavior ready. Run it from
WSL/Windows with the real Electron overlay visible, not just renderer smoke
coverage.

Start from a known-good live overlay:

```bash
hermes-pet doctor
hermes-pet launch --replace
hermes-pet overlay-status
```

- Confirm `launch --replace` closes stale or duplicate overlays, leaves one
  visible overlay connected to `ws://127.0.0.1:17473`, and does not leave an
  orphaned Electron window after a second replace.
- Emit or trigger `job_started` and confirm the pet enters the working/running
  state, shows a concise job bubble or status card, and records the job in the
  tray/history view.
- Trigger `job_finished` with a successful wrapped command and confirm the pet
  returns from working state, shows success feedback, and groups the completed
  job with the prior start event instead of creating a confusing duplicate item.
- Trigger `job_failed` with an expected failing wrapped command and confirm the
  pet shows failure feedback, the tray item is easy to distinguish from success,
  and the overlay attention border appears when the failure needs review.
- Emit `approval_needed` and confirm the review/attention state is visible, the
  tray groups the approval request clearly, and the attention border remains
  noticeable without blocking the desktop.
- Send `message_received` with `--urgent` and confirm it cuts through quiet or
  muted non-critical handling, produces visible attention feedback, and remains
  grouped with message activity in the tray.
- Emit `daily_brief` with `hermes-pet brief --emit` and confirm the summary is
  readable in the overlay, does not look urgent unless it contains urgent
  content, and appears as brief activity in the tray.
- Exercise tray grouping by creating a start, finish, failure, approval, urgent
  message, and daily brief in one session; confirm related job events collapse
  together while distinct attention types remain scannable.
- Switch profiles with `hermes-pet profile focus`, `pairing`, `demo`, and
  `silent`; confirm each profile changes bubble/attention behavior as expected
  and `hermes-pet profile normal` restores ordinary behavior.
- Toggle quiet modes with `hermes-pet quiet`, `hermes-pet quiet --silent`, and
  `hermes-pet quiet --off`; confirm non-critical bubbles are reduced or hidden
  while urgent messages, failures, and approvals still surface appropriately.
- Test reconnect by stopping or closing the overlay/bridge boundary, restarting
  with `hermes-pet launch` or `hermes-pet launch --replace`, and confirming new
  events appear without needing to clear local state.
- Select a valid custom pet, relaunch with `hermes-pet launch --replace`, and
  confirm it animates for idle, work, success, failure, attention, and message
  states. Then select or simulate an invalid/missing custom pet and confirm the
  overlay falls back to the built-in pet instead of rendering blank.

Useful manual event commands:

```bash
hermes-pet emit approval_needed "Manual approval check"
hermes-pet message --source telegram --sender "Ada" --urgent "Production is blocked"
hermes-pet brief --emit
hermes-pet wrap --name "Manual success" -- true
hermes-pet wrap --name "Manual failure" -- false
```

## Daily Workflow

Use the pet as a lightweight activity layer:

```bash
hermes-pet status
hermes-pet emit bubble "Starting work"
hermes-pet brief
```

Keep the overlay running in the background. Use `wrap` or `run` for work you want in job history.

## Custom Pets

Install animated custom pets outside the repo:

```bash
hermes-pet custom-pet validate <path>
hermes-pet custom-pet import <path> --name <name>
hermes-pet custom-pet use <name>
hermes-pet custom-pet current
```

Custom pets live under `${HERMES_PET_HOME:-~/.hermes_pet}/custom-pets/<name>/`. Use `hermes-pet custom-pet list` to see installed pets and `hermes-pet custom-pet remove <name>` to delete one.

A tiny repo fixture is available for validating the custom pet path without
generating art:

```bash
hermes-pet custom-pet validate docs/fixtures/custom-pets/minimal-spark
hermes-pet custom-pet import docs/fixtures/custom-pets/minimal-spark --name minimal-spark
hermes-pet custom-pet use minimal-spark
hermes-pet launch --replace
```

## Wrapping Work

Wrap named work:

```bash
hermes-pet wrap --name "API tests" -- pytest
```

Run a command with an inferred name:

```bash
hermes-pet run -- npm test
```

Hermes Pets records start, success, failure, duration, exit code, and a redacted command. Sensitive-looking flags are not retryable.

Retry the latest safe failed job:

```bash
hermes-pet retry
```

## Messages

Send a message notification:

```bash
hermes-pet message --source telegram --sender "Ada" "Can you review this?"
```

Mark it urgent when it should cut through quiet handling:

```bash
hermes-pet message --source telegram --sender "Ada" --urgent "Production is blocked"
```

## Quiet and Mute

Use named profiles when you want predictable notification behavior:

```bash
hermes-pet profile --list
hermes-pet profile normal
hermes-pet profile focus
hermes-pet profile pairing
hermes-pet profile demo
hermes-pet profile silent
```

Use quiet mode for fewer bubbles:

```bash
hermes-pet quiet
```

Silence non-critical bubbles:

```bash
hermes-pet quiet --silent
```

Return to normal:

```bash
hermes-pet quiet --off
```

Mute temporarily:

```bash
hermes-pet mute 30m
hermes-pet mute 2h
```

Inspect preferences:

```bash
hermes-pet prefs
hermes-pet prefs profile focus
```

## Checking Jobs

Show recent jobs:

```bash
hermes-pet jobs
```

Show the latest job in detail:

```bash
hermes-pet jobs --last
```

Show failures only:

```bash
hermes-pet jobs --failed
hermes-pet jobs --failed --last
```

Scan a subset by status or text:

```bash
hermes-pet jobs --status succeeded
hermes-pet jobs --query tests
```

## Brief and Recap

Summarize recent activity:

```bash
hermes-pet brief
hermes-pet brief --since 2h
hermes-pet brief --since 7d
```

Emit the brief to the overlay:

```bash
hermes-pet brief --emit
```

Print a compact text version for chat:

```bash
hermes-pet brief --telegram-text
```

## Troubleshooting

Duplicate overlay:

```bash
hermes-pet overlay-status
hermes-pet launch --replace
```

Invisible sprite:

```bash
hermes-pet launch --replace
hermes-pet emit bubble "Sprite check"
hermes-pet doctor
```

If it is still invisible, check whether the overlay window is off-screen. The position file is in `~/.hermes_pet/overlay-position.json` unless `HERMES_PET_HOME` is set.

If a custom pet does not appear, run:

```bash
hermes-pet custom-pet current
hermes-pet custom-pet validate ~/.hermes_pet/custom-pets/<name>
hermes-pet launch --replace
```

Invalid custom pets are ignored so built-in species continue to work.

Bridge unavailable:

```bash
hermes-pet doctor
hermes-pet launch
hermes-pet overlay-status
```

If `emit`, `message`, or `brief --emit` says the bridge is unavailable, the overlay event bridge is not reachable at `ws://127.0.0.1:17473` or the port set by `HERMES_PET_PORT`.

CI-style diagnostics:

```bash
hermes-pet doctor --strict
```

Default `doctor` prints warnings but exits successfully so daily operators can
read the report without breaking a shell flow. `--strict` returns non-zero when
any check warns.

WSL-to-Windows launch failure:

```bash
hermes-pet doctor
hermes-pet overlay-status
command -v powershell.exe
```

`hermes-pet launch` needs the WSL bridge, Windows PowerShell, and Windows process
tools to agree. A sanitized shell is fine, but it still needs the Windows
PowerShell and system directories on `PATH`.

Prefs or jobs look wrong:

```bash
hermes-pet prefs
hermes-pet jobs --last
hermes-pet doctor
hermes-pet state export --since 24h
hermes-pet state cleanup --dry-run --keep-jobs 50 --keep-events 100
```

State is stored under `~/.hermes_pet` by default. Set `HERMES_PET_HOME` only when you intentionally want a separate pet state.
