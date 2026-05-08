# Phase 5 Release Closeout

Phase 5 is release readiness and platform evidence. It should not bump the
package version, tag a release, push publish artifacts, or upload to PyPI unless
that becomes an explicit release task.

## Version Mechanics

Use semantic versioning for the next release decision:

- `0.1.1`: patch release for narrow fixes, documentation polish, and readiness
  improvements that do not materially change the public story.
- `0.2.0`: minor release for a public next release when platform support,
  install rehearsal, package artifact checks, contribution workflow, and closeout
  evidence are strong enough to describe a broader readiness milestone.

The Phase 5 implementation kept `project.version` unchanged by default. The
explicit release task on 2026-05-07 bumped `project.version` to `0.2.0`.

## Phase 5 Acceptance Evidence

| Area | Evidence target | Status |
| --- | --- | --- |
| Supported platform matrix | WSL/Windows is the only supported full-overlay platform; Linux/macOS/native Windows are investigated or unsupported unless proven | Documented in `docs/platform-support.md` |
| GitHub install readiness | GitHub install remains the primary supported install path; wheel/sdist and packaged overlay artifacts are checked | Documented; artifact verifier added |
| PyPI and installer notes | Metadata gaps improved where low-risk; future install paths compared; no PyPI publish | Documented in `docs/packaging-decision-notes.md` |
| Community custom pets | Issue/PR workflow covers package files, validation, previews, licensing, and curation; no hosted gallery | Documented in `docs/custom-pet-contributions.md` |
| Readiness stack | Required commands pass before push | Passed on 2026-05-07 |

## Required Readiness Stack

Run before pushing Phase 5:

```bash
pytest
node scripts/smoke-renderer.js
scripts/verify-packaged-overlay.sh
scripts/smoke-hermes-pet.sh --temp-state
scripts/verify-live-overlay.sh
```

Run `scripts/verify-live-overlay.sh` when the local machine can launch the real
WSL/Windows overlay. If it skips because Windows interop is unavailable, record
that exact result instead of treating it as full live evidence.

Additional package evidence:

```bash
python3 scripts/verify-package-artifacts.py
```

## 2026-05-07 Verification

Passed:

```bash
.venv/bin/pytest
node scripts/smoke-renderer.js
.venv/bin/python scripts/verify-package-artifacts.py
PYTHON=.venv/bin/python scripts/verify-packaged-overlay.sh
PYTHON=.venv/bin/python scripts/smoke-hermes-pet.sh --temp-state
PYTHON=.venv/bin/python scripts/verify-live-overlay.sh
HERMES_PET_INSTALL_TARGET=/home/tony/projects/hermes-pet scripts/smoke-github-install.sh
```

Notes:

- `pytest` was run from a local `.venv` because the base WSL Python did not have
  pytest installed and is externally managed.
- `scripts/smoke-hermes-pet.sh --temp-state` intentionally did not launch the
  bridge, so it reported bridge-unavailable warnings while still passing CLI and
  state smoke coverage.
- `scripts/verify-live-overlay.sh` passed on WSL/Windows and verified overlay
  launch, bridge connection, custom pet fallback, event forwarding, attention
  tray state, disconnect, reconnect, and cleanup.
- The install smoke used the current workspace as `HERMES_PET_INSTALL_TARGET`
  because the Phase 5 branch had not been pushed yet.

## Release Decision

Released as `0.2.0` after the explicit release task on 2026-05-07.

The evidence supports a minor release rather than `0.1.1` because Phase 5 now
defines the public support boundary, proves WSL/Windows live overlay behavior,
checks wheel and sdist contents, preserves GitHub install as the supported path,
documents PyPI/installer decisions, and adds a curated community custom pet
workflow.

Use `0.1.1` only if the release task intentionally narrows scope to documentation
and patch-level packaging cleanup without presenting Phase 5 as the next public
readiness release.

## v0.3.0 Dashboard Release Readiness

The v0.3.0 dashboard milestone is prepared as a public release candidate after
the explicit 2026-05-08 release-readiness task. GitHub release/tagging should
still be a deliberate release operation after the worktree is clean. PyPI upload
and installer publishing remain out of scope.

Scope completed:

- Localhost-only `hermes-pet dashboard` with per-process token auth.
- Static dashboard overview with pet state, selected custom pet, prefs summary,
  recent jobs/events, bridge status, and achievement preview.
- Change Pet dashboard APIs and UI for replacing the active built-in pet,
  random hatch, confirmation copy, and custom visual clearing.
- Custom pet dashboard APIs and UI for typed-path import, select, clear, remove,
  list, invalid state display, and overlay test event.
- Preferences APIs and UI for profile, quiet mode, tray-on-urgent, idle bubbles,
  throttle, and bridge-offline-safe saves.
- Opt-in voice preview CLI/API/UI with adapter command, env override, stdin text,
  metadata env vars, allowlisted events, timeout handling, and explicit test.
- Foundational achievement ledger with idempotent unlocks and simple overlay
  event handling.
- Dashboard package-data verification for wheel and sdist artifacts.
- Dashboard visual QA screenshots under `docs/assets/hermes-pets-dashboard-v030-*.png`
  with evidence in `docs/dashboard-v030-qa.md`.

Out of scope remains explicit: PyPI, installer publishing, hosted gallery,
drag/drop import, full voice mode, and rich achievement celebrations.

Release readiness stack passed on 2026-05-08:

```bash
python3 -m compileall -q src/hermes_pet
uv run pytest
node --check overlay/src/renderer.js
node --check overlay/src/main.js
node --check overlay/src/main.windows.js
node --check overlay/src/preload.js
node --check src/hermes_pet/dashboard/app.js
node scripts/smoke-renderer.js
bash -n shell-helpers/hermes-pet.bash scripts/smoke-hermes-pet.sh scripts/smoke-github-install.sh scripts/verify-packaged-overlay.sh scripts/verify-live-overlay.sh
python3 scripts/validate-sprite-manifest.py
scripts/smoke-hermes-pet.sh --temp-state
scripts/smoke-hermes-pet.sh --fresh-install
scripts/verify-packaged-overlay.sh
python3 scripts/verify-package-artifacts.py
scripts/verify-live-overlay.sh
HERMES_PET_INSTALL_TARGET=/home/tony/projects/hermes-pet scripts/smoke-github-install.sh
hermes-pet doctor
```

Results:

- `uv run pytest`: 64 passed.
- Package artifact inspection built and verified v0.3.0 wheel and sdist files.
- Live overlay verification passed on WSL/Windows, including launch, bridge
  connection, custom pet fallback, success/failure/attention event forwarding,
  attention tray state, bridge disconnect, reconnect, and cleanup.
- Local GitHub-style install smoke passed with
  `HERMES_PET_INSTALL_TARGET=/home/tony/projects/hermes-pet`.
- `hermes-pet doctor` reported `Doctor result: ready.`

Release decision: v0.3.0 is ready for an explicit GitHub tag/release operation
after final clean-tree verification. PyPI and installer publishing are deferred.
