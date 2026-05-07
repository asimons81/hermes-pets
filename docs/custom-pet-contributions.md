# Community Custom Pet Contributions

Phase 5 supports a contribution workflow for custom pet packages. It does not
add a hosted gallery, remote upload flow, or automatic asset distribution.

## Submission Path

1. Open a "Custom pet" issue with the proposed pet name, description, included
   animation states, asset license, attribution, and preview evidence.
2. Wait for basic curation feedback when the pet introduces a new style,
   questionable licensing, large assets, or unusual animation states.
3. Open a focused pull request with the package files only after the package
   validates locally.
4. Include validation output, preview screenshots or GIFs, and the environment
   used for testing.

## Required Package Contents

- `custom-pet.json` with a safe lowercase package name and state definitions.
- `sprites/idle/*.png`; `idle` is the only required animation state.
- Optional state folders such as `run_right`, `run_left`, `waving`, `jumping`,
  `failed`, `waiting`, `running`, `review`, `message_react`, `bubble_react`, or
  `blink`.
- `README.md` for the pet when attribution, generation notes, or review context
  would help maintainers.
- `contact-sheet.png`, screenshots, or a GIF when available.

## Required Evidence

Run at least:

```bash
hermes-pet custom-pet validate <path>
hermes-pet custom-pet preview <path> --output /tmp/<pet-name>-preview.html
```

For live overlay evidence on the supported platform, use a temporary state
directory so the review does not depend on your daily pet selection:

```bash
preview_home="$(mktemp -d)"
HERMES_PET_HOME="$preview_home" hermes-pet custom-pet import <path> --name <pet-name>
HERMES_PET_HOME="$preview_home" hermes-pet custom-pet use <pet-name>
HERMES_PET_HOME="$preview_home" hermes-pet launch --replace
HERMES_PET_HOME="$preview_home" hermes-pet emit bubble "Custom pet preview"
HERMES_PET_HOME="$preview_home" hermes-pet close --bridge
```

## Licensing and Attribution

Contributors must have the right to submit every asset. Acceptable submissions
include original work, properly licensed open assets, or generated assets with
clear permission for redistribution in this repository. Include attribution,
source links, and license names where applicable.

Do not submit copyrighted characters, trademarked mascots, scraped art, or
generated assets with unclear redistribution rights.

## Curation Expectations

Maintainers may ask for changes when a package:

- Fails validation or relies on unsafe names/paths.
- Is too large for a practical package fixture or built-in asset.
- Has unclear licensing or attribution.
- Has unreadable frames, inconsistent crop/scale, or animations that are hard to
  interpret in the small overlay.
- Duplicates an existing pet without a clear improvement.
- Requires platform behavior beyond the supported WSL/Windows overlay path.

Accepted custom pets are curated repository contributions, not automatically
published gallery entries.
