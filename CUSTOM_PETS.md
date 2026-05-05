# Hermes Pet Custom Pets

Hermes Pet custom pets are animated sprite packages installed outside the repo, under the active state directory:

```text
${HERMES_PET_HOME:-~/.hermes_pet}/custom-pets/<pet-name>/
```

This keeps user-generated pets separate from tracked built-in assets.

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
hermes-pet custom-pet use my-fox
hermes-pet custom-pet current
hermes-pet custom-pet remove my-fox
```

The bridge sends the selected custom pet package to the overlay on connect. If validation or loading fails, the overlay keeps using the built-in pet species.

## Create With Codex

Use the repo-local skill:

```text
.codex/skills/hermes-pet-hatch/SKILL.md
```

The skill uses the existing `hatch-pet` workflow for generation and QA, then packages the finalized frames into the Hermes format.

Useful helper scripts:

```bash
python scripts/package-custom-pet.py --source output/hatch-pet-runs/<slug> --name <slug> --output output/hermes-pet-hatch/<slug>/package
python scripts/package-custom-pet.py --builtin-species fox --name fox-fixture --output output/hermes-pet-hatch/fox-fixture/package
python scripts/validate-custom-pet.py output/hermes-pet-hatch/<slug>/package
```

Keep generated work in `output/`. Install only when you want to use a package locally.

## Known Limitations

- There is no rich visual preview command yet; use the generated contact sheet, validate the package, then import and launch the overlay for a live check.
- Custom pet selection is local state under `~/.hermes_pet` and does not add the package to the built-in species manifest.
