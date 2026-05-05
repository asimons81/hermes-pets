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
```

Close only the overlay:

```bash
hermes-pet close
```

Add `--bridge` only when you also want to stop the event bridge.

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

Prefs or jobs look wrong:

```bash
hermes-pet prefs
hermes-pet jobs --last
hermes-pet doctor
```

State is stored under `~/.hermes_pet` by default. Set `HERMES_PET_HOME` only when you intentionally want a separate pet state.
