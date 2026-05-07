# Hermes Pets Platform Support Matrix

Phase 5 support is based on verified release-readiness evidence, not assumed
portability. WSL/Windows is the supported platform for the full Hermes Pets
experience. Native Linux and macOS remain investigation targets until the launch,
overlay, and verification paths are proven end to end.

## Support Levels

- Supported: documented install path, CLI behavior, bridge behavior, overlay
  launch, packaged overlay assets, and smoke/live verification have passing
  evidence.
- Investigated: part of the stack is expected to run or has been inspected, but
  full overlay behavior is not proven.
- Unsupported: known launch requirements are missing or unimplemented.

## Current Matrix

| Platform | Install mode | CLI and state | Bridge | Overlay launch | Live verifier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| WSL2 on Windows 10/11 with Windows interop | GitHub `pip install 'git+https://github.com/asimons81/hermes-pets.git'`, local editable install, or local non-editable install | Supported | Supported on `127.0.0.1` | Supported through `powershell.exe` and `overlay/scripts/launch-windows-overlay.ps1` | Supported with `scripts/verify-live-overlay.sh` when Windows interop is available | Full supported platform |
| Native Windows PowerShell or cmd.exe | Not the primary path | Investigated only | Investigated only | Unsupported by the Python launcher because the current flow expects the CLI to run from WSL and call Windows interop tools | Not covered | Unsupported for Phase 5 |
| Native Linux desktop | Local Python install is expected to cover CLI-only commands | Investigated only | Likely runnable for local CLI/bridge checks | Unsupported: no native Linux Electron launcher, process matching, or desktop verification contract is implemented | Skips outside WSL | CLI-only investigation target |
| macOS | Local Python install is expected to cover CLI-only commands | Investigated only | Likely runnable for local CLI/bridge checks | Unsupported: no macOS Electron launcher, process matching, or desktop verification contract is implemented | Skips outside WSL | CLI-only investigation target |

## Behavior Boundaries

CLI-only commands include `status`, `hatch`, `prefs`, `jobs`, `brief`,
`custom-pet validate`, `custom-pet preview`, and local state export/cleanup.
These commands may work anywhere Python 3.10+ and the package dependencies are
available, but Phase 5 does not claim native Linux or macOS support for them
without dedicated install rehearsal evidence.

Full overlay behavior means all of the following pass together:

- `hermes-pet launch` starts or reuses the Python bridge.
- The Windows Electron overlay opens from WSL through PowerShell.
- `hermes-pet overlay-status`, `hermes-pet close`, and `hermes-pet close --bridge`
  can find and control the overlay process.
- Renderer events, custom-pet fallback, reconnect, and attention/tray state are
  verified by `scripts/verify-live-overlay.sh`.

## Known Platform Blockers

- Native Linux needs an Electron launcher, process discovery/close behavior, and
  a live overlay verifier that proves visible desktop behavior.
- macOS needs the same launcher, process discovery/close behavior, and live
  verifier work using macOS desktop conventions.
- Native Windows needs a first-class Python execution path outside WSL before it
  can share the supported install story.
- GitHub install is the supported install path for Phase 5; PyPI and desktop
  installers are packaging decisions for a later milestone.
