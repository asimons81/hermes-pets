# Hermes Pets v0.3.0 Dashboard QA

Issues: #52 Dashboard polish screenshots; #59 Dashboard pet-changing QA, docs, and release evidence; #63 Achievement unlock overlay notice

Date: 2026-05-08

## Environment

- Local checkout: `/home/tony/projects/hermes-pet`
- Temporary dashboard state: `/tmp/hermes-dashboard-qa-state-17476`
- Pet-changing temporary dashboard state: `/tmp/hermes-dashboard-petchange-qa-17477`
- Dashboard server: `hermes-pet dashboard --no-open --port 17476`
- Pet-changing dashboard server: `hermes-pet dashboard --no-open --port 17480`
- Screenshot runner: `/usr/bin/google-chrome` headless
- Sensitive data handling: screenshots were captured from a synthetic temporary
  state. The private token URL is not visible in the captured page content.

## Screenshots

Committed screenshot assets:

- `docs/assets/hermes-pets-dashboard-v030-overview.png` - 1440px overview release screenshot.
- `docs/assets/hermes-pets-dashboard-v030-overview-wide.png` - 1920px overview viewport.
- `docs/assets/hermes-pets-dashboard-v030-overview-laptop.png` - 1024px narrow-laptop viewport.
- `docs/assets/hermes-pets-dashboard-v030-overview-small.png` - 560px smaller supported viewport.
- `docs/assets/hermes-pets-dashboard-v030-custom-pets.png` - Custom Pets empty state and import form.
- `docs/assets/hermes-pets-dashboard-v030-change-pet.png` - Change Pet built-in species catalog and random hatch controls.
- `docs/assets/hermes-pets-dashboard-v030-custom-pets-selected.png` - Custom Pets selected custom visual with non-destructive clear action.
- `docs/assets/hermes-pets-dashboard-v030-preferences.png` - Preferences controls.
- `docs/assets/hermes-pets-dashboard-v030-voice.png` - Voice preview controls.
- `docs/assets/hermes-pets-dashboard-v030-achievements.png` - Achievement ledger.

## States Covered

- Populated overview with active pet, job metrics, succeeded job, failed retryable job, event log, bridge offline state, and achievements.
- Custom Pets empty state.
- Change Pet populated species catalog with current built-in species marked, adopt/restart actions, and random hatch.
- Custom Pets selected custom visual state with `Use built-in pet`, `Clear`, and destructive `Remove` controls visually separated.
- Pet replacement confirmation copy is implemented in the dashboard JavaScript and states that XP, stats, and milestones reset, installed packages are kept, and the current custom visual selection is cleared.
- API/test coverage includes no active pet adoption, existing pet replacement/reset, invalid species, bad JSON, random hatch, clear current custom visual, and token protection.
- Preferences populated from default local prefs.
- Voice preview disabled/default state.
- Achievements mixed locked/unlocked state, plus quiet overlay unlock notice copy: `Achievement unlocked: Clean Run`.
- Achievement unlock notice non-goals: no confetti, sound, modal, or added artwork/assets; muted, quiet, and silent notification modes suppress the non-critical bubble/tray popover.
- Responsive overview at 1920px, 1440px, 1024px, and 560px widths.

## Verification Commands

```bash
python3 -m compileall -q src/hermes_pet
uv run pytest
node --check overlay/src/renderer.js
node --check overlay/src/main.js
node --check overlay/src/main.windows.js
node --check overlay/src/preload.js
node --check src/hermes_pet/dashboard/app.js
node scripts/smoke-renderer.js
bash -n shell-helpers/hermes-pet.bash scripts/smoke-hermes-pet.sh scripts/smoke-github-install.sh scripts/verify-packaged-overlay.sh scripts/verify-live-overlay.sh
python3 scripts/validate-sprite-manifest.py
scripts/smoke-hermes-pet.sh --temp-state
scripts/smoke-hermes-pet.sh --fresh-install
scripts/verify-packaged-overlay.sh
python3 scripts/verify-package-artifacts.py
scripts/verify-live-overlay.sh
HERMES_PET_INSTALL_TARGET=/home/tony/projects/hermes-pet scripts/smoke-github-install.sh
hermes-pet doctor
```

Results:

- `node --check src/hermes_pet/dashboard/app.js`: passed.
- `python3 -m compileall -q src/hermes_pet`: passed.
- `uv run pytest`: 64 passed.
- Overlay and dashboard JavaScript syntax checks: passed.
- Shell release-script syntax checks: passed.
- `python3 scripts/validate-sprite-manifest.py`: passed, 4 species and 43 species-state entries.
- `node scripts/smoke-renderer.js`: passed, `renderer smoke ok`.
- `scripts/smoke-hermes-pet.sh --temp-state`: passed, `Hermes Pets smoke complete`.
- `scripts/smoke-hermes-pet.sh --fresh-install`: passed from a temporary venv.
- `scripts/verify-packaged-overlay.sh`: passed, `packaged overlay ok`.
- `python3 scripts/verify-package-artifacts.py`: passed for v0.3.0 wheel and sdist inspection, `package artifacts ok`.
- `scripts/verify-live-overlay.sh`: passed, including launch, bridge connect,
  custom pet fallback, event forwarding, attention tray, bridge disconnect,
  reconnect, and cleanup.
- `HERMES_PET_INSTALL_TARGET=/home/tony/projects/hermes-pet scripts/smoke-github-install.sh`: passed.
- `hermes-pet doctor`: passed, `Doctor result: ready.`

## Visual Findings

- No obvious overlapping controls, clipped button text, broken sprites, or unreadable primary text were found in the captured screenshots.
- The pet now anchors the overview at desktop widths and stacks predictably at the smaller supported width.
- The Change Pet catalog uses compact rows with stable adopt/restart buttons and no table-like admin treatment.
- The Custom Pets selected state clearly separates non-destructive visual clearing from destructive package removal.
- The achievement unlock notice is grouped separately in the overlay activity tray and remains informational rather than attention/critical.
- The jobs feed wraps long job names without overlapping the timestamp/retryable chips.
- The local/token security framing remains visible without exposing the token itself.

## Residual Risk

- A live manual browser keyboard walkthrough remains useful for confirmation
  cancel/accept ergonomics, but the API paths and release stack passed.
- API error and auth-failure UI paths are implemented and covered by tests, but the committed screenshot set focuses on release-safe populated/empty local states. Token URLs were intentionally not captured.
- Live overlay verification passed separately from the screenshot pass on 2026-05-08.
