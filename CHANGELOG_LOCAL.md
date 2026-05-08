# Hermes Pets Local Changelog

This file records local implementation milestones and release-candidate notes alongside Git history.

## 2026-05-05 Consolidation Snapshot

- Reworked `README.md` to describe the current daily-use tool: install, launch, events, wrapped jobs, retry, messages, quiet/mute prefs, brief, doctor, shell helpers, smoke script, and WSL/Windows operation.
- Added `CURRENT_STATE.md` as a recovery-oriented snapshot of working features, key commands, important files, limitations, and next improvements.
- Added this local changelog for future recovery without Git history.

## Implemented Milestones

## v0.3.0 - 2026-05-08

- Released the dashboard milestone as the v0.3.0 public release candidate.
- Added `hermes-pet dashboard`, a localhost-only, token-protected operator dashboard.
- Added dashboard state, custom pet, preferences, voice preview, achievements, and test-event APIs.
- Added packaged static dashboard assets with artifact verification for wheel and sdist builds.
- Added typed-path custom pet import/select/remove from the dashboard; drag/drop import and hosted gallery remain out of scope.
- Added opt-in voice preview plumbing with `voice-prefs.json`, `hermes-pet voice ...`, `HERMES_PET_TTS_COMMAND`, event allowlisting, stdin text, metadata env vars, timeout handling, and dashboard controls.
- Added foundational achievements in `achievements.json` with idempotent unlocks and simple overlay `achievement_unlocked` handling.
- Added dashboard visual design spec and screenshot smoke helper for desktop/mobile QA evidence.
- Bumped package metadata from `0.2.0` to `0.3.0`; PyPI upload and installer publishing remain out of scope.

## v0.2.0 - 2026-05-07

- Released Phase 5 as the public readiness baseline for WSL2/Windows full-overlay support.
- Kept GitHub install as the supported public install path.
- Added package artifact checks for wheel and sdist contents.
- Added PyPI and installer decision notes without publishing to PyPI.
- Added curated community custom pet contribution workflow.
- Bumped package metadata from `0.1.0` to `0.2.0`.

### Phase 5 Release Readiness

- Added a platform support matrix that names WSL2/Windows as the supported
  full-overlay platform and keeps native Linux, macOS, and native Windows as
  investigation or unsupported targets.
- Added wheel/sdist artifact verification and documented GitHub install as the
  supported public install path for Phase 5.
- Added PyPI and installer decision notes, with metadata improvements but no
  PyPI publish.
- Added community custom pet contribution docs and issue/PR checklists for
  validation, preview evidence, licensing, and curated review.
- Added Phase 5 closeout notes recommending `0.2.0` for the next release after
  the 2026-05-07 readiness stack passed.

### Movement Fix

- Overlay positioning and drag handling were corrected so the pet window can be moved and its position can be saved.
- Window bounds are clamped against the visible work area to recover from off-screen or stale positions.

### Visibility Fix

- Sprite visibility and bounds handling were corrected so the rendered pet remains visible inside the transparent Electron window.
- Overlay recovery guidance now points to `hermes-pet launch --replace`, `emit bubble`, and `doctor`.

### Event Surface

- Added a normalized local event schema with support for ambient activity and operator events.
- Supported event types include `bubble`, `status`, `job_started`, `job_finished`, `job_failed`, `job_history`, `approval_needed`, `message_received`, and `daily_brief`.
- CLI events are appended to local history and sent to the bridge when available.

### Wrap and Run

- Added `hermes-pet wrap --name "Job" -- command...`.
- Added `hermes-pet run -- command...` with inferred or optional names.
- Wrapped commands emit lifecycle events and optional long-running status events.
- Output/error summaries are captured and redacted when appropriate.

### Jobs and Retry

- Added recent job history in local state.
- Added `hermes-pet jobs`, `jobs --last`, `jobs --failed`, and `jobs --limit`.
- Added `hermes-pet retry` for the latest safe failed job.
- Sensitive-looking command arguments are redacted and marked non-retryable.

### Single-Instance Launch

- Added `hermes-pet launch` as the main bridge-plus-overlay entry point.
- Added Windows/WSL PowerShell launcher support for the Electron overlay.
- Added `hermes-pet launch --replace` to stop existing overlay process trees before launching a fresh overlay.
- Added `hermes-pet overlay-status` for bridge and Windows overlay process visibility.

### Messages

- Added `hermes-pet message` for external message notifications.
- Messages include source, sender, body, urgency, and optional open-command metadata.
- Urgent messages use warning severity.

### Quiet and Mute

- Added persistent notification preferences.
- Added `hermes-pet quiet`, `quiet --silent`, and `quiet --off`.
- Added `hermes-pet mute <duration>` for temporary non-urgent bubble suppression.
- Added `hermes-pet prefs` and `prefs set` for inspecting and updating preferences.

### Brief

- Added `hermes-pet brief` to summarize recent jobs and events.
- Added `brief --since`, `brief --emit`, and `brief --telegram-text`.
- Brief output highlights latest status, failures, successes, pending approvals, recent messages, and suggested next action.

### Operator Layer

- Added `hermes-pet doctor` for local diagnostics.
- Added `OPERATOR_GUIDE.md` for daily operation.
- Added Bash helpers in `shell-helpers/hermes-pet.bash`.
- Added `scripts/smoke-hermes-pet.sh` for quick end-to-end verification.
