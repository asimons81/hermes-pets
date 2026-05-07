# Contributing to Hermes Pets

Hermes Pets is a local-first animated desktop companion for agent and terminal workflows. It combines a Python CLI, a WebSocket bridge, local job/event state, and an Electron overlay so local work can feel visible, friendly, and easier to follow.

This is a small open-source project. Contributions are welcome, especially when they keep the tool easy to install, easy to understand, and dependable during real terminal work.

## Good First Contribution Areas

- Bug fixes
- README and docs polish
- CLI help text
- Bridge unavailable error messages
- Overlay reliability
- WSL/Windows launch documentation
- Custom pet examples
- Sprite and animation polish
- Smoke tests

## Project Principles

- Local-first: Hermes Pets should work without hosted services or remote accounts.
- CLI-first: terminal commands should remain the primary control surface.
- Small dependency surface: avoid new dependencies unless they clearly pay for themselves.
- No telemetry by default.
- No private Hermes config or machine-specific paths in committed docs, examples, tests, or code.
- Fun, but reliable: animation and personality are part of the project, but they should not make operator workflows brittle.

## Development Setup

Clone the repo and install the Python package in editable mode:

```bash
git clone https://github.com/asimons81/hermes-pets.git
cd hermes-pets
python -m pip install -e ".[dev]"
```

If you use `uv`, an editable tool install is also supported:

```bash
uv tool install --editable .
```

The Python package exposes two console commands:

```bash
hermes-pet
hermes-pet-bridge
```

The Electron overlay is managed separately under `overlay/`. On WSL/Windows, run the CLI from WSL; `hermes-pet launch` starts the local Python bridge and opens the Windows overlay through the PowerShell launcher.

## Smoke Tests

Use the commands below as a practical local check before opening a pull request. Some overlay commands require your local bridge and Windows/WSL overlay environment to be available.

```bash
hermes-pet --help
hermes-pet doctor
hermes-pet prefs
hermes-pet overlay-status
hermes-pet launch --replace
hermes-pet emit bubble "Smoke test"
hermes-pet close --bridge
hermes-pet run -- /bin/echo "run smoke"
hermes-pet wrap --name "failure smoke" -- /bin/false
hermes-pet jobs --last
hermes-pet custom-pet validate <path-to-custom-pet-package>
```

`custom-pet validate` expects a package directory, such as a folder containing `custom-pet.json` and sprite frames.

There is also a repo smoke script:

```bash
scripts/smoke-hermes-pet.sh
```

## Pull Request Expectations

Please include:

- A clear description of what changed.
- Why the change is needed.
- Commands you used to test it.
- Screenshots or GIFs for overlay, sprite, or animation changes.
- The OS/environment you tested, especially whether WSL2 and Windows overlay launch were involved.

Keep pull requests focused. For large behavior changes, open an issue first so the direction can be discussed before a big patch lands.

## Custom Pet Contributions

Custom pet contributions are curated issue/PR submissions. Start with the
"Custom pet" issue template, then open a focused pull request after the package
validates locally. See `docs/custom-pet-contributions.md` for the full workflow.

Custom pet contributions should include:

- `custom-pet.json`.
- Sprite files for the included states/animations, including `sprites/idle/*.png`.
- Output from `hermes-pet custom-pet validate <path>`.
- Preview evidence from `hermes-pet custom-pet preview <path> --output ...`.
- License and attribution details for every asset.

Do not submit copyrighted characters, trademarked mascots, scraped art, or generated assets with unclear licensing unless you own the rights or have explicit permission to contribute them.

Hermes Pets does not run a hosted custom pet gallery in Phase 5. Accepted pets
are reviewed repository contributions.

## What Probably Will Not Be Accepted

- Cloud-only features.
- Telemetry by default.
- Large rewrites without prior discussion.
- Breaking CLI changes without migration notes.
- Generated assets with unclear licensing.
- Changes that assume Tony's private Hermes setup, private config, or local machine paths.
