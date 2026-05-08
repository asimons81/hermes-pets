# Hermes Pets v0.3.0 Dashboard QA

Issue: #52 Dashboard polish: visual QA and release screenshots

Date: 2026-05-08

## Environment

- Local checkout: `/home/tony/projects/hermes-pet`
- Temporary dashboard state: `/tmp/hermes-dashboard-qa-state-17476`
- Dashboard server: `hermes-pet dashboard --no-open --port 17476`
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
- `docs/assets/hermes-pets-dashboard-v030-preferences.png` - Preferences controls.
- `docs/assets/hermes-pets-dashboard-v030-voice.png` - Voice preview controls.
- `docs/assets/hermes-pets-dashboard-v030-achievements.png` - Achievement ledger.

## States Covered

- Populated overview with active pet, job metrics, succeeded job, failed retryable job, event log, bridge offline state, and achievements.
- Custom Pets empty state.
- Preferences populated from default local prefs.
- Voice preview disabled/default state.
- Achievements mixed locked/unlocked state.
- Responsive overview at 1920px, 1440px, 1024px, and 560px widths.

## Verification Commands

```bash
node --check src/hermes_pet/dashboard/app.js
uv run pytest
node scripts/smoke-renderer.js
scripts/smoke-hermes-pet.sh --temp-state
scripts/verify-packaged-overlay.sh
python3 scripts/verify-package-artifacts.py
```

Results:

- `node --check src/hermes_pet/dashboard/app.js`: passed.
- `uv run pytest`: 48 passed.
- `node scripts/smoke-renderer.js`: passed, `renderer smoke ok`.
- `scripts/smoke-hermes-pet.sh --temp-state`: passed. The expected bridge-unavailable warnings appeared because the live overlay was not launched.
- `scripts/verify-packaged-overlay.sh`: passed.
- `python3 scripts/verify-package-artifacts.py`: passed for wheel and sdist inspection.

## Visual Findings

- No obvious overlapping controls, clipped button text, broken sprites, or unreadable primary text were found in the captured screenshots.
- The pet now anchors the overview at desktop widths and stacks predictably at the smaller supported width.
- The jobs feed wraps long job names without overlapping the timestamp/retryable chips.
- The local/token security framing remains visible without exposing the token itself.

## Residual Risk

- A live manual browser keyboard walkthrough is still recommended before final release approval.
- API error and auth-failure UI paths are implemented, but the committed screenshot set focuses on release-safe populated/empty local states. Token URLs were intentionally not captured.
- Live overlay verification is outside this screenshot pass; `scripts/smoke-hermes-pet.sh --temp-state` reported expected bridge-unavailable warnings because the overlay was not launched.
