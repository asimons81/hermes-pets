# Custom Pet Release Checklist

Use this checklist when adding or publishing a new curated custom pet package.

## Package shape

- Create `docs/custom-pets/<slug>/`.
- Include `custom-pet.json`, `README.md`, and `sprites/<state>/*.png`.
- Keep the slug lowercase and safe for install paths.
- Include `idle` and the other supported states you actually want to ship.

## Validation

```bash
hermes-pet custom-pet validate docs/custom-pets/<slug>
hermes-pet custom-pet preview docs/custom-pets/<slug> --output /tmp/<slug>-preview.html
```

For extra safety, rehearse the install/use path in a temporary state directory:

```bash
preview_home="$(mktemp -d)"
HERMES_PET_HOME="$preview_home" hermes-pet custom-pet import docs/custom-pets/<slug> --name <slug>
HERMES_PET_HOME="$preview_home" hermes-pet custom-pet use <slug>
HERMES_PET_HOME="$preview_home" hermes-pet launch --replace
HERMES_PET_HOME="$preview_home" hermes-pet emit bubble "Custom pet preview"
HERMES_PET_HOME="$preview_home" hermes-pet close --bridge
```

## Release notes and version surfaces

- Update `CHANGELOG_LOCAL.md` with the new release entry.
- Add a `docs/releases/vX.Y.Z.md` note that explains what shipped and what stayed out of scope.
- Bump the project version in `pyproject.toml` when the release is public.
- Refresh any user-facing docs that still describe only the previous gallery state.

## Repository checks

```bash
python3 -m compileall -q src/hermes_pet
uv run pytest
python3 scripts/validate-custom-pet.py docs/custom-pets/<slug>
git diff --check
```

If the repo has a lockfile, run the lock check too:

```bash
uv lock --check
```

If the release includes publishable GitHub assets, attach them only after the repo commit, tag, and release note are ready.
