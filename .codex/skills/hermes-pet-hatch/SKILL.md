---
name: hermes-pet-hatch
description: Create Hermes Pet-compatible custom animated pet packages from text prompts, references, or hatch-pet finalized runs. Use when a user wants to generate, package, validate, preview, import, or install custom Hermes Pet animated pets without modifying built-in repo assets.
---

# Hermes Pet Hatch

## Purpose

Create animated pets for Hermes Pet's overlay runtime. This skill is a Hermes-specific adapter around the general `hatch-pet` workflow: use `hatch-pet` for visual generation and row QA, then package the finalized frames into a Hermes custom pet package that can be imported with `hermes-pet custom-pet import <path> --name <name>`.

Do not add generated pets to `overlay/assets/sprites/` by default. Built-in assets are repo-owned. Custom pets should be packaged under `output/` first and installed into the user's Hermes Pet state directory only when asked.

## Package Format

A Hermes custom pet package is a directory with this shape:

```text
custom-pet.json
sprites/
  idle/
    idle_00.png
    idle_01.png
  run_right/
    run_right_00.png
  run_left/
    run_left_00.png
contact-sheet.png       optional
README.md               optional
```

`custom-pet.json`:

```json
{
  "version": 1,
  "name": "pet-slug",
  "source_format": "hatch-pet",
  "states": {
    "idle": { "fps": 4, "loop": true, "frames": ["idle_00.png"] },
    "waving": { "fps": 8, "loop": false, "fallback": "idle", "frames": ["waving_00.png"] }
  }
}
```

Required:

- `idle` state with at least one real PNG frame.
- Safe lowercase package name: `a-z`, `0-9`, `_`, `-`; starts with a letter or number.
- Safe PNG filenames without path separators or traversal.

Optional supported states:

- `run_right`
- `run_left`
- `waving`
- `jumping`
- `failed`
- `waiting`
- `running`
- `review`
- `message_react`
- `bubble_react`
- `blink`

Do not fabricate unsupported states such as `drag`, `hover`, `walk_left`, or `walk_right` unless the runtime and package validator explicitly support them for the current request.

## Workflow

1. Gather the pet concept, references, display name, and package slug.

If the user does not provide a name, infer a short name from the concept. Keep the slug lowercase and safe. Put all generated work in `output/hermes-pet-hatch/<slug>/` or `output/hatch-pet-runs/<slug>/`.

2. Use the installed `hatch-pet` skill for visual generation.

Read and follow:

```text
${CODEX_HOME:-$HOME/.codex}/skills/hatch-pet/SKILL.md
```

Use its normal image generation, row prompt, mirroring, finalization, contact sheet, and review rules. Do not draw, tile, or synthesize replacement visuals with local scripts. Only mirror `run_left` from `run_right` when the hatch-pet rules say the pet is safe to mirror.

3. Generate only Hermes-supported rows.

Map hatch-pet row names to Hermes states:

```text
idle           -> idle
running-right  -> run_right
running-left   -> run_left
waving         -> waving
jumping        -> jumping
failed         -> failed
waiting        -> waiting
running        -> running
review         -> review
```

Missing optional states are acceptable because the overlay falls back to `idle` or the manifest state's fallback. Do not invent `drag`, `hover`, or walk rows just to fill gaps.

4. Package the finalized run.

Preferred command:

```bash
python scripts/package-custom-pet.py \
  --source output/hatch-pet-runs/<slug> \
  --name <slug> \
  --output output/hermes-pet-hatch/<slug>/package
```

For a built-in fixture or compatibility test:

```bash
python scripts/package-custom-pet.py \
  --builtin-species fox \
  --name fox-fixture \
  --output output/hermes-pet-hatch/fox-fixture/package
```

5. Validate the package.

```bash
python scripts/validate-custom-pet.py output/hermes-pet-hatch/<slug>/package
hermes-pet custom-pet validate output/hermes-pet-hatch/<slug>/package
```

Validation must pass before calling the pet ready. It checks required `idle`, real PNG signatures, safe filenames, safe state names, and manifest-compatible state metadata.

6. Preview and inspect.

Use the hatch-pet contact sheet and videos from the finalized run first. If a package includes `contact-sheet.png`, inspect it before import. Confirm identity consistency, transparent backgrounds, readable small silhouette, and state-specific motion.

7. Import only when requested or when the task explicitly includes installation.

```bash
hermes-pet custom-pet import output/hermes-pet-hatch/<slug>/package --name <slug>
hermes-pet custom-pet use <slug>
hermes-pet custom-pet current
```

The import destination is outside the repo under the active Hermes Pet state dir:

```text
${HERMES_PET_HOME:-~/.hermes_pet}/custom-pets/<slug>/
```

## Verification

For creation-only work:

```bash
python3 -m compileall -q src/hermes_pet
python3 scripts/validate-custom-pet.py output/hermes-pet-hatch/<slug>/package
```

For runtime/import work:

```bash
hermes-pet custom-pet validate output/hermes-pet-hatch/<slug>/package
hermes-pet custom-pet import output/hermes-pet-hatch/<slug>/package --name <slug>
hermes-pet custom-pet use <slug>
hermes-pet custom-pet current
node --check overlay/src/renderer.js overlay/src/main.js overlay/src/main.windows.js overlay/src/preload.js
python3 scripts/validate-sprite-manifest.py
hermes-pet doctor
```

Keep generated packages and hatch outputs in `output/`. Do not push, tag, or add remotes.
