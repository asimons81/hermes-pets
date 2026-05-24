# Archived Hermes Pets Clean Install Rehearsal

Date: 2026-05-05

This is historical evidence from 2026-05-05. It verified a non-editable install from a fresh environment outside the repository and is not current install guidance. It did not push, tag, publish, or add remotes.

## Supported Install Path

For the Phase 5 rehearsal, GitHub install was the supported public install path:

```bash
python3 -m venv /tmp/hermes-pet-release-rehearsal-venv
/tmp/hermes-pet-release-rehearsal-venv/bin/python -m pip install \
  'git+https://github.com/asimons81/hermes-pets.git'
/tmp/hermes-pet-release-rehearsal-venv/bin/hermes-pet --help
```

PyPI packaging can be rehearsed and improved, but this rehearsal did not publish to
PyPI or treat `pip install hermes-pet` as the supported install path.

For this local release-candidate rehearsal, the package was installed
non-editably from the repository path:

```bash
python3 -m venv /tmp/hermes-pet-release-rehearsal-20260505-1745-venv
/tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/python -m pip install <repo>
```

The installed wheel was `hermes_pet-0.1.0-py3-none-any.whl`; `websockets-16.0`
was installed from pip cache.

## Environment

```bash
VENV=/tmp/hermes-pet-release-rehearsal-20260505-1745-venv
STATE=/tmp/hermes-pet-release-rehearsal-20260505-1745-state
FIXTURE=/tmp/hermes-pet-release-rehearsal-20260505-1745-fixture
PORT=18473
```

All installed CLI checks were run from `/tmp`, outside the repository, using the
venv executable directly and a temp state directory:

```bash
cd /tmp
HERMES_PET_HOME=/tmp/hermes-pet-release-rehearsal-20260505-1745-state \
HERMES_PET_FORCE_PACKAGED_OVERLAY=1 \
HERMES_PET_PORT=18473 \
/tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/hermes-pet --help
```

## Commands Run

```bash
python3 -m venv /tmp/hermes-pet-release-rehearsal-20260505-1745-venv
/tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/python -m pip install <repo>

cd /tmp
HERMES_PET_HOME=/tmp/hermes-pet-release-rehearsal-20260505-1745-state HERMES_PET_FORCE_PACKAGED_OVERLAY=1 HERMES_PET_PORT=18473 /tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/hermes-pet --help
HERMES_PET_HOME=/tmp/hermes-pet-release-rehearsal-20260505-1745-state HERMES_PET_FORCE_PACKAGED_OVERLAY=1 HERMES_PET_PORT=18473 /tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/hermes-pet doctor
HERMES_PET_HOME=/tmp/hermes-pet-release-rehearsal-20260505-1745-state HERMES_PET_FORCE_PACKAGED_OVERLAY=1 HERMES_PET_PORT=18473 /tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/hermes-pet overlay-status

env PATH=/tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/mnt/c/Windows/System32/WindowsPowerShell/v1.0:/mnt/c/Windows/system32 HERMES_PET_HOME=/tmp/hermes-pet-release-rehearsal-20260505-1745-state HERMES_PET_FORCE_PACKAGED_OVERLAY=1 HERMES_PET_PORT=18473 /tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/hermes-pet doctor

/tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/python <repo>/scripts/package-custom-pet.py --builtin-species fox --name install-rehearsal-fox --output /tmp/hermes-pet-release-rehearsal-20260505-1745-fixture
HERMES_PET_HOME=/tmp/hermes-pet-release-rehearsal-20260505-1745-state HERMES_PET_FORCE_PACKAGED_OVERLAY=1 HERMES_PET_PORT=18473 /tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/hermes-pet custom-pet validate /tmp/hermes-pet-release-rehearsal-20260505-1745-fixture

find /tmp/hermes-pet-release-rehearsal-20260505-1745-state/cache/overlay -maxdepth 3 -type f | sort | sed -n "1,120p"

env PATH=/tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/mnt/c/Windows/System32/WindowsPowerShell/v1.0:/mnt/c/Windows/system32 HERMES_PET_HOME=/tmp/hermes-pet-release-rehearsal-20260505-1745-state HERMES_PET_FORCE_PACKAGED_OVERLAY=1 HERMES_PET_PORT=18473 HERMES_PET_SPECIES=fox /tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/hermes-pet launch --replace
env PATH=/tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/mnt/c/Windows/System32/WindowsPowerShell/v1.0:/mnt/c/Windows/system32 HERMES_PET_HOME=/tmp/hermes-pet-release-rehearsal-20260505-1745-state HERMES_PET_FORCE_PACKAGED_OVERLAY=1 HERMES_PET_PORT=18473 /tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/hermes-pet overlay-status
HERMES_PET_HOME=/tmp/hermes-pet-release-rehearsal-20260505-1745-state HERMES_PET_FORCE_PACKAGED_OVERLAY=1 HERMES_PET_PORT=18473 /tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/hermes-pet emit bubble Install\ rehearsal\ smoke
env PATH=/tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/mnt/c/Windows/System32/WindowsPowerShell/v1.0:/mnt/c/Windows/system32 HERMES_PET_HOME=/tmp/hermes-pet-release-rehearsal-20260505-1745-state HERMES_PET_FORCE_PACKAGED_OVERLAY=1 HERMES_PET_PORT=18473 /tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/hermes-pet close --bridge
env PATH=/tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/mnt/c/Windows/System32/WindowsPowerShell/v1.0:/mnt/c/Windows/system32 HERMES_PET_HOME=/tmp/hermes-pet-release-rehearsal-20260505-1745-state HERMES_PET_FORCE_PACKAGED_OVERLAY=1 HERMES_PET_PORT=18473 /tmp/hermes-pet-release-rehearsal-20260505-1745-venv/bin/hermes-pet overlay-status
```

For the archived Phase 5 GitHub install rehearsal, use:

```bash
scripts/smoke-github-install.sh
```

In the archived rehearsal, set `HERMES_PET_INSTALL_TARGET` for a branch, tag, fork, or local path while keeping the same smoke workflow.

## Passed

- `hermes-pet --help` worked from `/tmp` using the installed venv executable.
- `hermes-pet doctor` resolved packaged overlay assets into
  `/tmp/hermes-pet-release-rehearsal-20260505-1745-state/cache/overlay`.
- `hermes-pet overlay-status` worked before launch and reported no overlay
  processes.
- A temporary packaged custom pet fixture was created and validated by the
  installed CLI.
- Cached packaged overlay assets included `package.json`, renderer files,
  Windows launcher script, `assets/manifest.json`, and sprite assets.
- `hermes-pet launch --replace` started the bridge on `ws://127.0.0.1:18473`.
- Post-launch `overlay-status` reported exactly one overlay process, using the
  temp cached packaged overlay path:
  `/tmp/hermes-pet-release-rehearsal-20260505-1745-state/cache/overlay/src/main.windows.js`.
- `hermes-pet emit bubble Install\ rehearsal\ smoke` reached the live bridge and
  returned `Emitted bubble: Install rehearsal smoke`.
- `hermes-pet close --bridge` stopped the overlay process tree and one bridge
  process.
- Final `overlay-status` reported bridge unavailable and overlay processes none.

## Known Caveats

- Invoking the venv executable directly does not put the venv on `PATH`. In that
  mode, `doctor` still runs from the venv Python but its `hermes-pet command`
  check may report another `hermes-pet` found on `PATH`. Prepending the venv bin
  directory makes the doctor command check point at the rehearsal executable.
- A sanitized `PATH` must still include
  `/mnt/c/Windows/System32/WindowsPowerShell/v1.0` and `/mnt/c/Windows/system32`
  on WSL/Windows, or `doctor`, `overlay-status`, `launch`, and `close` cannot
  find the Windows PowerShell overlay launcher.
- `emit` requires a running bridge. Use `launch` before treating `emit` as a live
  overlay smoke test.
- The Windows Electron dependency cache is shared at
  `%LOCALAPPDATA%\HermesAgent\pet-overlay-electron`, but the
  overlay process itself was matched and controlled by the temp packaged overlay
  path, avoiding the normal installed Hermes Pets state.
