# Hermes Pets Release Checklist

Use this before a public release candidate. Do not push, tag, or publish from this checklist unless that is the explicit release task.

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
bash -n shell-helpers/hermes-pet.bash scripts/smoke-hermes-pet.sh scripts/smoke-github-install.sh
python3 scripts/validate-sprite-manifest.py
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

## Installability

- Confirm `pyproject.toml` exposes `hermes-pet` and `hermes-pet-bridge`.
- Confirm Python dependencies match the import surface.
- Confirm overlay dependencies in `overlay/package.json` still match the Windows launcher cache install.
- Confirm `scripts/verify-packaged-overlay.sh` passes and reports a cached packaged overlay path.
- Editable installs should still resolve the repo-local `overlay/`; non-editable installs should resolve packaged overlay assets copied under `~/.hermes_pet/cache/overlay`.

## Safety

- Generated output, caches, local state, node_modules, and env/secrets are ignored.
- No obvious secrets are tracked.
- Custom pet names, state folders, and PNG frame filenames reject traversal or unsafe names.
- The bridge defaults to `127.0.0.1`.
- `hermes-pet state export` is documented as redacted diagnostics, not backup.
- Backup/restore docs copy `${HERMES_PET_HOME:-~/.hermes_pet}` directly and preserve the current state before restore.

## Known Release Gaps

- Custom package preview exists, but richer playback controls and side-by-side state comparison remain future improvements.
