# Hermes Pets Packaging and Installer Decision Notes

Phase 5 improves packaging evidence without publishing a PyPI release or
building a desktop installer. GitHub install remains the supported public install
path until a later milestone proves broader distribution.

## Current Supported Path

```bash
python3 -m pip install 'git+https://github.com/asimons81/hermes-pets.git'
```

Use `scripts/smoke-github-install.sh` to rehearse this path in a fresh virtual
environment. Set `HERMES_PET_INSTALL_TARGET` to a branch, tag, fork, or local
path when validating a release candidate before merge.

## Package Readiness

Low-risk metadata added for PyPI readiness:

- Project URLs for homepage, source, issues, changelog, and documentation.
- Keywords covering the local desktop companion, CLI, Electron overlay, and
  WSL/Windows launch surface.
- Classifiers for Python version, license, OS audience, environment, and
  development status.

Artifact checks:

- `python3 scripts/verify-package-artifacts.py` builds and inspects wheel and
  sdist archives.
- `scripts/verify-packaged-overlay.sh` installs non-editably and verifies the
  packaged overlay cache path.
- `scripts/smoke-github-install.sh` rehearses fresh install behavior from the
  supported GitHub target.

## Install Path Comparison

| Path | Pros | Cons | Phase 5 decision |
| --- | --- | --- | --- |
| `pip install git+https://...` | Works before PyPI publish; points directly at the canonical repo; easy to rehearse by branch or tag | Requires Git/network access; less friendly than a package index release; users must trust the repo ref | Supported primary path |
| `pipx install git+https://...` | Isolates CLI dependencies; natural for command-line tools | Needs the same GitHub target; overlay still depends on WSL/Windows launch requirements | Good candidate for documented operator install once rehearsed |
| `uv tool install git+https://...` | Fast isolated CLI install; good for local developer workflows | Requires `uv`; should be rehearsed against GitHub refs and packaged overlay assets | Good candidate for documented developer/operator install once rehearsed |
| PyPI package | Familiar `pip install hermes-pet`; easier dependency resolution and repeatable version pins | Requires publishing process, project ownership, release signing/checks, and long-description verification | Prepare metadata now; do not publish in Phase 5 |
| Windows desktop installer | Friendliest full-overlay onboarding for the supported platform | Requires packaging Electron, update/uninstall story, signing decision, and Windows-native QA | Future platform bet after GitHub and PyPI evidence |
| Native Linux/macOS installer | Could expand desktop audience | Native overlay launch and verification are unproven | Do not pursue before platform support is proven |

## Recommendation

The next formal packaging milestone should be "Phase 6: Public packaging and
installer proof." It should:

- Tag a release candidate from a clean GitHub install rehearsal.
- Rehearse `pipx` and `uv tool` installs from the GitHub tag.
- Run `python3 scripts/verify-package-artifacts.py` and check README rendering
  before any PyPI upload.
- Decide whether PyPI is enough for the next public release or whether a Windows
  desktop installer should be treated as a separate follow-up.
- Keep Linux/macOS installers out of scope until native overlay support is
  proven.
