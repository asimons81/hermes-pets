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
