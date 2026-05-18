# Hermes Pets Custom Pets

Hermes Pets custom pets are animated sprite packages installed outside the repo, under the active state directory:

```text
${HERMES_PET_HOME:-~/.hermes_pet}/custom-pets/<pet-name>/
```

This keeps user-generated pets separate from tracked built-in assets.

Community contribution rules live in `docs/custom-pet-contributions.md`. Phase 5
supports curated issue/PR submissions only; it does not add a hosted gallery or
remote upload flow.

## Package Format

A custom pet package can be a finalized `hatch-pet` run, or a Hermes package with:

```text
custom-pet.json
sprites/
  idle/
    idle_00.png
  run_right/
    run_right_00.png
contact-sheet.png optional
README.md optional
```

`idle` is required. Optional supported states are `run_right`, `run_left`, `waving`, `jumping`, `failed`, `waiting`, `running`, `review`, `message_react`, `bubble_react`, and `blink`. Missing optional states fall back to `idle` or the state fallback.

Names must use lowercase letters, numbers, `_`, and `-`, and must start with a letter or number. PNG filenames must be simple safe filenames with no path separators.

## CLI

```bash
hermes-pet custom-pet list
hermes-pet custom-pet validate output/hatch-pet-runs/fox
hermes-pet custom-pet import output/hatch-pet-runs/fox --name my-fox
hermes-pet custom-pet codex
hermes-pet custom-pet import-codex latest --use
hermes-pet custom-pet use my-fox
hermes-pet custom-pet current
hermes-pet custom-pet remove my-fox
```

Using a custom pet writes it as the canonical active pet in `pet.json` with species `custom`, and the bridge sends that active pet plus its package manifest to the overlay on connect. If validation or loading fails, Hermes Pets refuses activation rather than silently showing the wrong companion.

## Preview Workflow

Generate a standalone HTML animation preview before importing a package:

```bash
hermes-pet custom-pet preview <path> --output /tmp/custom-pet-preview.html
hermes-pet custom-pet preview --installed <name> --output /tmp/custom-pet-preview.html
```

The preview validates the package, embeds the available PNG frames, lists fps,
loop/fallback settings, and calls out missing optional states. Missing optional
states are valid and fall back to `idle` or the state's configured fallback.

Use a temporary state directory when you also want to prove the same bridge and
renderer path the real overlay uses:

```bash
preview_home="$(mktemp -d)"
HERMES_PET_HOME="$preview_home" hermes-pet custom-pet validate <path>
HERMES_PET_HOME="$preview_home" hermes-pet custom-pet import <path> --name preview-pet
HERMES_PET_HOME="$preview_home" hermes-pet custom-pet preview --installed preview-pet --output /tmp/preview-pet.html
HERMES_PET_HOME="$preview_home" hermes-pet custom-pet use preview-pet
HERMES_PET_HOME="$preview_home" hermes-pet launch --replace
HERMES_PET_HOME="$preview_home" hermes-pet emit bubble "Preview check"
```

This leaves your daily `${HERMES_PET_HOME:-~/.hermes_pet}` selection alone. Close
the preview overlay when done:

```bash
HERMES_PET_HOME="$preview_home" hermes-pet close --bridge
```

When a generated package includes `contact-sheet.png`, inspect that first for
obvious frame, scale, or cropping problems. The live preview is still the final
check because it proves Electron can load the selected package and animate the
fallbacks.

## Template Workflow

Use the repo template as the smallest hand-built starter package:

```text
docs/templates/custom-pets/basic/
  custom-pet.json
  sprites/
    idle/
      idle_00.png
  README.md
```

Copy that folder outside the repo or into `output/`, rename the package in
`custom-pet.json`, replace `sprites/idle/idle_00.png`, then add optional state
folders as you create animation frames. Validate and preview after each
meaningful change:

```bash
hermes-pet custom-pet validate output/hermes-pet-hatch/<slug>/package
hermes-pet custom-pet preview output/hermes-pet-hatch/<slug>/package --output /tmp/<slug>-preview.html
```

Keep generated or experimental template work in `output/` so the repository does
not collect local art runs.

## Create With Codex

Use the repo-local skill:

```text
.codex/skills/hermes-pet-hatch/SKILL.md
```

The skill uses the existing `hatch-pet` workflow for generation and QA, then packages the finalized frames into the Hermes format. `hermes-pet custom-pet codex` lists importable Codex desktop pets found under `CODEX_HOME/pets`, `~/.codex/pets`, and `/mnt/c/Users/*/.codex/pets`; `hermes-pet custom-pet import-codex <slug|latest|path> --use` imports one directly into the active state directory and activates it immediately. Use `--include-repo-output` only when intentionally scanning repo-local output candidates.

Useful helper scripts:

```bash
python3 scripts/package-custom-pet.py --source output/hatch-pet-runs/<slug> --name <slug> --output output/hermes-pet-hatch/<slug>/package
python3 scripts/package-custom-pet.py --builtin-species fox --name fox-fixture --output output/hermes-pet-hatch/fox-fixture/package
python3 scripts/validate-custom-pet.py output/hermes-pet-hatch/<slug>/package
```

Keep generated work in `output/`. Install only when you want to use a package locally.

## Minimal Fixture

The repo includes a tiny curated package for documentation, validation, and
operator trust checks:

```text
docs/fixtures/custom-pets/minimal-spark/
  custom-pet.json
  sprites/
    idle/
      idle_00.png
  README.md
```

Validate it with either the public CLI command or the repo helper:

```bash
hermes-pet custom-pet validate docs/fixtures/custom-pets/minimal-spark
python3 scripts/validate-custom-pet.py docs/fixtures/custom-pets/minimal-spark
```

Use an isolated state directory when you want to rehearse import/use without
touching your daily pet selection:

```bash
HERMES_PET_HOME=/tmp/hermes-pet-fixture-state hermes-pet custom-pet import docs/fixtures/custom-pets/minimal-spark --name minimal-spark
HERMES_PET_HOME=/tmp/hermes-pet-fixture-state hermes-pet custom-pet use minimal-spark
HERMES_PET_HOME=/tmp/hermes-pet-fixture-state hermes-pet custom-pet current
```

The fixture is intentionally minimal: one valid idle PNG, one metadata file, and
no optional animation states. It proves the package contract without adding a
generated pet run to the repository.

## Known Limitations

- Use `hermes-pet custom-pet preview` for an HTML animation check, then import into a temporary `HERMES_PET_HOME` and launch the overlay for a live check when desktop behavior matters.
- Custom pet activation is local state under `~/.hermes_pet`; it writes the active pet as species `custom` and does not add the package to the built-in species manifest.
- Community custom pet submissions are reviewed as ordinary repository
  contributions. There is no hosted gallery, in-app downloader, or remote upload
  path in Phase 5.
