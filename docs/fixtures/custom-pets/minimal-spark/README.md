# Minimal Spark Custom Pet Fixture

This is the smallest curated Hermes Pets custom pet package in the repo. It is
for validation and import rehearsals, not for showcasing generated art.

Validate from the repository root:

```bash
hermes-pet custom-pet validate docs/fixtures/custom-pets/minimal-spark
python3 scripts/validate-custom-pet.py docs/fixtures/custom-pets/minimal-spark
```

Rehearse import without changing your normal pet state:

```bash
HERMES_PET_HOME=/tmp/hermes-pet-fixture-state hermes-pet custom-pet import docs/fixtures/custom-pets/minimal-spark --name minimal-spark
HERMES_PET_HOME=/tmp/hermes-pet-fixture-state hermes-pet custom-pet use minimal-spark
HERMES_PET_HOME=/tmp/hermes-pet-fixture-state hermes-pet custom-pet current
```

The `idle` state is required by the validator. Optional animation states are
omitted on purpose so this fixture also exercises idle fallback behavior.
