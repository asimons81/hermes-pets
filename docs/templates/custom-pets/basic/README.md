# Basic Custom Pet Template

Copy this folder when starting a Hermes Pets animated custom pet.

The template is intentionally tiny: one valid `idle` frame plus a
`custom-pet.json` manifest. Replace the placeholder PNG with your own frame,
then add optional state folders under `sprites/` as your animation grows.

Common optional states:

- `run_right`
- `run_left`
- `running`
- `waiting`
- `failed`
- `review`
- `waving`
- `jumping`
- `message_react`
- `bubble_react`
- `blink`

Validate and preview from the repository root:

```bash
hermes-pet custom-pet validate docs/templates/custom-pets/basic
hermes-pet custom-pet preview docs/templates/custom-pets/basic --output /tmp/basic-pet-preview.html
```

Rehearse import without changing your normal pet state:

```bash
HERMES_PET_HOME=/tmp/hermes-pet-template-state hermes-pet custom-pet import docs/templates/custom-pets/basic --name basic
HERMES_PET_HOME=/tmp/hermes-pet-template-state hermes-pet custom-pet preview --installed basic --output /tmp/basic-installed-preview.html
HERMES_PET_HOME=/tmp/hermes-pet-template-state hermes-pet custom-pet use basic
```
