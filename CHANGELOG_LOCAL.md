# Hermes Pets Local Changelog

This file records local implementation milestones and release-candidate notes alongside Git history.

## 2026-05-05 Consolidation Snapshot

- Reworked `README.md` to describe the current daily-use tool: install, launch, events, wrapped jobs, retry, messages, quiet/mute prefs, brief, doctor, shell helpers, smoke script, and WSL/Windows operation.
- Added `CURRENT_STATE.md` as a recovery-oriented snapshot of working features, key commands, important files, limitations, and next improvements.
- Added this local changelog for future recovery without Git history.

## Implemented Milestones

## v0.7.0 - 2026-06-05

### Added

- Added an unsigned beta native Windows desktop installer path that bundles the Electron overlay, `hermes-pet.exe`, and `hermes-pet-bridge.exe`.
- Added native Windows installer build, verification, CI artifact, and release documentation.
- Added installed-mode launcher support so native Windows `launch`, `overlay-status`, `close`, `close --bridge`, and `doctor` work against the bundled app.

### Changed

- Bumped package metadata from `0.6.2` to `0.7.0` for the native Windows installer release.
- Upgraded overlay runtime dependencies to Electron `42.3.3` and `ws` `8.21.0`.
- Documented native Windows as an unsigned beta path while keeping WSL2/Windows as the stable full-overlay path.

## v0.6.2 - 2026-06-04

### Added

- Added Sam Altman, Elon Musk, and Jeff Bezos as repository-backed curated custom pet packages under `docs/custom-pets/`.
- Added per-pet README files, Codex source metadata, spritesheets, extracted sprite frames, and static site preview assets for the new packages.
- Added a public release note for the gallery expansion release.

### Changed

- Bumped package metadata from `0.6.1` to `0.6.2` for the gallery expansion release.
- Updated the custom pet gallery index and static site release strip to reflect the expanded package set.

## v0.6.1 - 2026-05-24

### Added

- Added the curated custom pet gallery under `docs/custom-pets/` with Freddy, Jason, and Leatherface as repository-backed downloadable packages.
- Added per-pet READMEs, a gallery index, and a release checklist so future custom pets can be added without inventing a new workflow.
- Added a public release note for the gallery release.

### Changed

- Bumped package metadata from `0.6.0` to `0.6.1` for the gallery release.
- Kept the release focused on the gallery and documentation, not a hosted downloader or in-app gallery backend.

## v0.6.0 - 2026-05-24

### Added

- Added the local recap export flow: render a deterministic static recap card from local session state, package it into a local bundle, and expose it through the narrow `hermes-pet recap export` CLI entry point.
- Added `recap-card.png`, `caption.txt`, and `metadata.json` as the export bundle shape for shareable local handoff and manual review.
- Added deterministic tests for the recap card renderer, export bundle shape, and export flow.

### Fixed

- Fixed the final review polish gap on the recap export card so the source window label reads cleanly and the card reads like a product artifact instead of a dashboard screenshot.

### Changed

- Bumped package metadata and lockfile version surfaces to `0.6.0` for the recap export release.
- Kept the release local-first, with hosted sharing, accounts, public posting, dashboard redesign, motion-first default, platform expansion, PyPI publish, and installer work out of scope.


## v0.5.0 - 2026-05-20

### Added

- Added the Codex custom-pet trust release path: discover Codex desktop pets, import by slug/latest/direct path, activate, preview, and verify in the live WSL/Windows overlay.
- Added dashboard Import From Codex support with source labels, direct-path selection for duplicate candidates, custom install names, replace behavior, and bridge-offline truth in success feedback.
- Added v0.5.0 release evidence under `docs/releases/v0.5.0.md`, including the T1-T4 Codex readiness packet and live overlay evidence path.

### Fixed

- Repaired the actual editable uv-tool runtime by reinstalling `hermes-pet` with Pillow present, preventing false confidence from ambient system Python.
- Hardened duplicate Codex candidate handling so WSL and Windows stores are distinguishable instead of showing repeated ambiguous slugs.
- Improved dashboard duplicate-name errors with actionable recovery guidance.
- Updated the live overlay verifier to accept the current `state` event shape for custom-pet selection, matching the bridge behavior exercised by T4/T6.

### Changed

- Bumped package metadata and lockfile from `0.4.1` to `0.5.0` for the release candidate.
- Kept PyPI, installer publishing, hosted gallery, drag/drop import, native platform expansion, full voice mode, rich achievements, and dashboard redesign out of scope.

## v0.4.1 - 2026-05-14

### Fixed

- Prepared a corrective release after the public v0.4.0 release-readiness audit found stale lockfile and release-lifecycle issues.
- Regenerated `uv.lock` so package metadata and lockfile version surfaces agree on `0.4.1`.
- Hardened WSL/Windows overlay shutdown so already-dead or slow-exiting Electron processes do not make cleanup fail spuriously.
- Hardened WSL/Windows overlay launch by mirroring renderer files into the Windows Electron cache before launch instead of running Electron directly against WSL UNC paths.
- Added bounded retry to the live overlay verifier for transient Windows/Electron startup and teardown races while still failing after repeated verifier failures.
- Improved update diagnostics so inherited `VIRTUAL_ENV` mismatches are reported instead of replacing the Python executable-derived environment truth.

### Changed

- Refreshed release-readiness docs with an accurate v0.4.1 corrective-release checklist and release-note draft.

## v0.4.0 - 2026-05-11

### Added

- Added guarded `hermes-pet update` command for safe update checks, dry runs, fast-forward-only git updates, dependency refreshes, and validation.

### Fixed

- Fixed version reporting for editable git checkout installs by preferring repo/source `pyproject.toml` over stale installed distribution metadata.

### Changed

- Improved `scripts/smoke-hermes-pet.sh` evidence output so release checks show PATH CLI version, source checkout version, selected command path, and temp-state behavior clearly.

## v0.3.0 - 2026-05-08

- Released the dashboard milestone as the v0.3.0 public release candidate.
- Added `hermes-pet dashboard`, a localhost-only, token-protected operator dashboard.
- Added dashboard state, custom pet, preferences, voice preview, achievements, and test-event APIs.
- Added packaged static dashboard assets with artifact verification for wheel and sdist builds.
- Added typed-path custom pet import/activate/remove from the dashboard; drag/drop import and hosted gallery remain out of scope.
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
