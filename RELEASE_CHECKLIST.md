# Hermes Pets Release Checklist

Use this before a public release candidate. Do not push, tag, or publish from this checklist unless that is the explicit release task.

## Repository

- `git status --short` is clean before and after verification.
- `git log --oneline -5` shows the intended release commits.
- `git remote -v` and `git tag --list` have no unexpected publish or tag state.

## Verification

```bash
python3 -m compileall -q src/hermes_pet
node --check overlay/src/renderer.js
node --check overlay/src/main.js
node --check overlay/src/main.windows.js
node --check overlay/src/preload.js
bash -n shell-helpers/hermes-pet.bash scripts/smoke-hermes-pet.sh
python3 scripts/validate-sprite-manifest.py
scripts/verify-packaged-overlay.sh
scripts/smoke-hermes-pet.sh
hermes-pet doctor
```

For custom package checks, validate an existing package or create a temporary built-in fixture:

```bash
fixture_dir="$(mktemp -d)/fox-fixture"
python3 scripts/package-custom-pet.py --builtin-species fox --name fox-fixture --output "$fixture_dir"
python3 scripts/validate-custom-pet.py "$fixture_dir"
```

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

## Known Release Gaps

- Rich custom package visual preview tooling is still missing.
