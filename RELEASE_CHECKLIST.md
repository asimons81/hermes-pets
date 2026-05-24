# Hermes Pets Release Checklist

Use this for release prep and verification. Do not push, tag, or publish from this checklist unless the release task explicitly asks for it.

## Repository

- `git status --short` is clean before and after verification.
- `git log --oneline -5` shows the intended release commits.
- `git remote -v` and `git tag --list` have no unexpected publish or tag state.

## Verification

```bash
python3 -m compileall -q src/hermes_pet
pytest
node --check overlay/src/renderer.js
node --check overlay/src/main.js
node --check overlay/src/main.windows.js
node --check overlay/src/preload.js
node scripts/smoke-renderer.js
bash -n shell-helpers/hermes-pet.bash scripts/smoke-hermes-pet.sh scripts/smoke-github-install.sh
python3 scripts/validate-sprite-manifest.py
python3 scripts/verify-package-artifacts.py
scripts/verify-packaged-overlay.sh
scripts/smoke-hermes-pet.sh --temp-state
hermes-pet doctor
```

These checks cover different confidence layers. The renderer smoke is headless
logic coverage, custom-pet validation/package commands prove package structure,
and `scripts/smoke-hermes-pet.sh --temp-state` proves CLI/state behavior in an
isolated state directory. They do not replace the live WSL/Windows overlay
verification in `OPERATOR_GUIDE.md`.

For custom package checks, validate an existing package or create a temporary built-in fixture:

```bash
fixture_dir="$(mktemp -d)/fox-fixture"
python3 scripts/package-custom-pet.py --builtin-species fox --name fox-fixture --output "$fixture_dir"
python3 scripts/validate-custom-pet.py "$fixture_dir"
hermes-pet custom-pet validate docs/fixtures/custom-pets/minimal-spark
```

For a public install rehearsal from GitHub:

```bash
scripts/smoke-github-install.sh
```

Set `HERMES_PET_INSTALL_TARGET` when rehearsing a branch, tag, fork, or local
path with the same script.

Before release, run the live overlay checklist from `OPERATOR_GUIDE.md` with the
real Electron window visible. Capture evidence for launch/replace, visible
sprite animation, tray grouping, attention borders, reconnect, quiet/profile
behavior, and custom pet fallback or preview.

## Phase 4 Closeout

For Hermes-aware integration work, keep the phase schema-first:

- Confirm event schema remains `hermes.pet.event.v1`.
- Confirm no live Hermes Agent, Nexus, Telegram, GitHub, calendar, or other
  adapter was added.
- Confirm project/session metadata comes from CLI flags, environment defaults,
  or safe git inference for `run` and `wrap`.
- Confirm action hints are stored and displayed only, never executed.
- Confirm `urgency` accepts only `normal`, `important`, and `urgent`.
- Confirm event history and state export keep only approved, redacted Phase 4
  metadata fields.
- Confirm briefs prioritize urgent/actionable local events and only group by
  project/session when useful.

Run the Phase 4 readiness stack before pushing:

```bash
pytest
node scripts/smoke-renderer.js
scripts/verify-packaged-overlay.sh
scripts/smoke-hermes-pet.sh --temp-state
scripts/verify-live-overlay.sh
```

Run `scripts/verify-live-overlay.sh` when the local machine can launch the real
overlay. If it is not available in a given environment, record that explicitly
with the rest of the verification output.

## Phase 5 Closeout

- Confirm `docs/platform-support.md` is current and does not overclaim native
  Linux, macOS, or native Windows support.
- Confirm `docs/packaging-decision-notes.md` keeps GitHub install primary and
  PyPI unpublished unless the release task explicitly changes that.
- Confirm `docs/custom-pet-contributions.md` describes curated repository
  contributions only, with no hosted gallery or upload flow.
- Run the Phase 5 readiness stack before pushing:

```bash
pytest
node scripts/smoke-renderer.js
scripts/verify-packaged-overlay.sh
scripts/smoke-hermes-pet.sh --temp-state
scripts/verify-live-overlay.sh
```

- Update `docs/release-closeout.md` and `CURRENT_STATE.md` with the evidence and
  the next-version recommendation.
- Do not bump `pyproject.toml` during Phase 5 by default.

## v0.5.0 Codex Custom-Pet Trust Closeout

- Confirm `pyproject.toml`, `uv.lock`, source-checkout CLI version, and release notes agree on `0.5.0`.
- Confirm the actual uv-tool runtime can import Pillow, not just ambient system Python:

```bash
/home/tony/.local/share/uv/tools/hermes-pet/bin/python -c "import PIL; print(PIL.__version__)"
```

- Run the Codex trust path in temporary state, using a real Codex desktop pet when available:

```bash
HERMES_PET_HOME="$(mktemp -d)" hermes-pet custom-pet codex
HERMES_PET_HOME="$(mktemp -d)" hermes-pet custom-pet import-codex <slug|latest|path> --name release-codex --use
```

- Confirm duplicate WSL/Windows Codex candidates show source labels and dashboard explicit choices use direct paths.
- Confirm dashboard Import From Codex handles empty state, populated state, latest, custom install name, duplicate without replace, duplicate with replace, use-after-import, bridge offline feedback, and selected custom pet sprite rendering.
- Confirm a live WSL/Windows overlay run proves a Codex-imported pet renders, event/bubble/failure/attention states don't blank it, bridge reconnect works, and removal/missing-custom-pet fallback survives.
- Use the evidence path in `docs/releases/v0.5.0.md` for the final release packet.
- Do not push, tag, publish a GitHub Release, upload to PyPI, build an installer, or claim native platform expansion without explicit approval.

## v0.3.0 Dashboard Release Closeout

- Confirm `hermes-pet dashboard` binds to localhost only, prints a private
  token URL, and rejects dashboard/API requests without the token.
- Confirm dashboard assets are present in editable installs, wheel artifacts,
  and sdist artifacts.
- Confirm voice preview is off by default, opt-in only, adapter-command based,
  and documented as preview plumbing.
- Confirm achievements remain foundational only: compact dashboard display,
  idempotent `achievements.json`, and simple bounded overlay event handling.
- Confirm custom pet dashboard import remains typed local path only. No drag/drop
  import, hosted gallery, upload flow, or remote dashboard scope.
- Capture dashboard QA screenshots for overview, change pet, custom pets,
  preferences, voice, achievements, populated state, empty state, and error
  state where practical. Check desktop and narrow/mobile viewports for overlap
  and clipped text.
- Run the v0.3.0 local readiness stack before release:

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
HERMES_PET_INSTALL_TARGET=<repo> scripts/smoke-github-install.sh
hermes-pet doctor
```

- For v0.3.0, GitHub release/tagging is allowed only as an explicit release
  operation after this stack passes and `git status --short` is clean. PyPI
  upload and installer publishing remain out of scope.

## Installability

- Confirm `pyproject.toml` exposes `hermes-pet` and `hermes-pet-bridge`.
- Confirm PyPI-facing metadata in `pyproject.toml` still matches the current
  supported platform claims and does not imply native Linux/macOS overlay
  support.
- Confirm Python dependencies match the import surface.
- Confirm overlay dependencies in `overlay/package.json` still match the Windows launcher cache install.
- Confirm `python3 scripts/verify-package-artifacts.py` builds and inspects both
  wheel and sdist contents, including Python modules, console-script metadata,
  overlay renderer files, Windows launcher script, manifest, and sprite PNGs.
- Confirm `scripts/verify-packaged-overlay.sh` passes and reports a cached packaged overlay path.
- Confirm `scripts/smoke-github-install.sh` passes for the public GitHub install
  path, or set `HERMES_PET_INSTALL_TARGET` to the exact branch/tag/fork being
  rehearsed.
- Editable installs should still resolve the repo-local `overlay/`; non-editable installs should resolve packaged overlay assets copied under `~/.hermes_pet/cache/overlay`.
- Confirm `docs/packaging-decision-notes.md` still names GitHub install as the
  supported path and records PyPI/installer work as a future milestone unless
  the release task explicitly changes that.

## Safety

- Generated output, caches, local state, node_modules, and env/secrets are ignored.
- No obvious secrets are tracked.
- Custom pet names, state folders, and PNG frame filenames reject traversal or unsafe names.
- The bridge defaults to `127.0.0.1`.
- `hermes-pet state export` is documented as redacted diagnostics, not backup.
- Backup/restore docs copy `${HERMES_PET_HOME:-~/.hermes_pet}` directly and preserve the current state before restore.

## Known Release Gaps

- Custom package preview exists, but richer playback controls and side-by-side state comparison remain future improvements.
