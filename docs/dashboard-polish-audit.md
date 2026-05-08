# Hermes Pets Dashboard Polish Audit

Issue: #43 Dashboard polish: audit current UI and technical structure

Date: 2026-05-08

## Summary

The v0.3.0 dashboard is a static HTML/CSS/vanilla JS console served by the Python
localhost-only, token-protected dashboard server. That architecture is the right
constraint for this milestone: polish should happen in `src/hermes_pet/dashboard/`
and preserve the current API contract in `src/hermes_pet/dashboard.py`.

The current UI is functional and already organized around Overview, Custom Pets,
Preferences, Voice, and Achievements, but it still reads as a generic dark admin
panel. The active pet appears as a small thumbnail in a metrics layout. Later
issues should make the pet the product centerpiece while keeping the console
dense, local, trustworthy, and keyboard-friendly.

## Files Reviewed

- `src/hermes_pet/dashboard/index.html`
- `src/hermes_pet/dashboard/app.css`
- `src/hermes_pet/dashboard/app.js`
- `src/hermes_pet/dashboard.py`
- `tests/test_v030_dashboard_preview.py`
- `README.md`
- `RELEASE_CHECKLIST.md`
- `docs/dashboard-design-spec.md`

No runtime screenshots were captured during this audit pass. Visual findings are
from static review of the dashboard source and existing product docs; screenshot
capture belongs to #52 once the redesigned states are stable.

## Current Architecture

- `index.html` defines one static app shell with five button-driven views:
  Overview, Custom Pets, Preferences, Voice, and Achievements.
- `app.js` reads the token from the query string or
  `hermes_pet_dashboard_token` cookie, sends it as `X-Hermes-Pet-Token`, fetches
  `/api/state`, and renders all dashboard views from the returned snapshot.
- `app.css` owns all styling through local CSS custom properties and component
  classes. There is no frontend build step, React, Tailwind, shadcn/ui, router,
  or icon dependency.
- `dashboard.py` serves static dashboard assets from the installed
  `hermes_pet.dashboard` package resources and overlay sprite assets from
  `hermes_pet.overlay.assets`.
- `DashboardHTTPServer` binds only to `127.0.0.1`, `localhost`, or `::1`, prints
  a per-process token URL, rejects unauthorized static and API requests, sets a
  strict same-site cookie when the valid token is supplied, and returns JSON API
  errors with `Cache-Control: no-store`.

## API And Data Contract

The primary frontend contract is `GET /api/state`, with schema
`hermes.pet.dashboard.v1`. The current snapshot includes:

- `generated_at`: UTC timestamp for the snapshot.
- `state_dir`: active Hermes Pets state directory.
- `server`: host, port, and `localhost_only` metadata.
- `pet`: current pet payload from `Pet.to_dict()`, plus `xp_next`; may be
  `null`.
- `custom_pet`: selected custom pet event payload; may be absent or empty.
- `custom_pets`: installed custom pet summaries, including validity and preview
  state summary where available.
- `prefs`: normalized notification preferences.
- `voice`: voice preview status.
- `jobs`: recent wrapped jobs, newest first.
- `job_summary`: `total`, `succeeded`, `failed`, and `retryable_failures`.
- `events`: recent local events, newest first.
- `achievements`: achievement items and unlock counts.
- `new_achievements`: achievements unlocked during snapshot sync.
- `bridge`: bridge host, port, availability, and optional error.

Additional endpoints currently used or available:

- `GET /api/prefs` and `POST /api/prefs`
- `GET /api/custom-pets`
- `GET /api/custom-pets/<name>/preview`
- `POST /api/custom-pets/import`
- `POST /api/custom-pets/use`
- `DELETE /api/custom-pets/<name>`
- `POST /api/events/test`
- `GET /api/voice`, `POST /api/voice`, and `POST /api/voice/test`
- `GET /api/achievements`
- `GET /overlay/assets/...` for packaged sprite assets

## UX And Visual Findings

- The left rail, panels, and metric cards are useful but still resemble a
  generic admin dashboard. The brand mark is a gradient square rather than a
  pet- or console-specific product signal.
- The palette is green-tinted overall. Green currently acts as brand, success,
  focus, selected segment, active bridge, and primary command color, which makes
  status semantics less clear.
- The active pet is constrained to a 96px sprite tile and competes with nested
  metric cards. It does not yet feel like the emotional or visual anchor of the
  overview.
- Metrics and jobs share repeated card treatments. Recent jobs should become a
  compact activity feed with status chips and structured metadata instead of
  repeated generic cards.
- Empty states exist and are better than blank panels, but they are visually
  generic and do not yet distinguish empty local state, bridge-offline state,
  API/auth failure, and stale data.
- The dashboard copy is mostly concise and local-aware. Later passes should keep
  the same professional tone and avoid marketing hero copy.

## Technical Findings

- Rendering responsibility is centralized in `app.js` functions:
  `renderSnapshot`, `renderPet`, `renderJobs`, `renderEvents`,
  `renderAchievements`, `renderCustomPets`, `hydratePrefs`, and `hydrateVoice`.
- The current implementation uses `innerHTML` heavily but escapes user-provided
  text with `escapeHtml()` before insertion. Dynamic URL usage is limited to
  encoded built-in sprite species and encoded custom pet API paths.
- `renderPet()` assumes built-in species sprites are available at
  `/overlay/assets/sprites/<species>.png`. Custom pet preview art is not exposed
  as a dashboard image URL today.
- `renderJobs()` uses available job fields: `name`, `id`, `status`,
  `exit_code`, `duration_text`, and `retryable`. It should not invent timestamps
  if the job payload lacks them.
- `generated_at` is already available and can support stale-state copy or a
  "last refreshed" display without backend changes.
- Current tests cover dashboard asset availability, token enforcement, empty and
  populated state snapshots, custom pet import, preferences, voice preview, and
  achievement idempotency.

## Accessibility And Responsive Findings

- Navigation, commands, segmented controls, inputs, and toggles use native
  interactive elements, which gives the redesign a solid semantic baseline.
- The active navigation state is visual only; `aria-current` or equivalent state
  text would make view changes clearer for assistive technology.
- The global alert uses `role="status"` but also reports errors. Error states
  may need `role="alert"` or clearer inline state depending on severity.
- Visible focus styling relies on browser defaults today. #44/#51 should define
  a strong focus token and apply it consistently to nav items, buttons, inputs,
  and segmented controls.
- Status dot meaning is mostly color-dependent. Bridge and job states should
  remain readable through text labels and chip copy, not color alone.
- Existing breakpoints at `860px` and `560px` are a reasonable starting point,
  but the five-column top nav can compress labels at narrow laptop/small browser
  widths. #50 should verify nav wrapping, panel widths, metric grids, and long
  job/custom pet names.
- If #54 adds motion, it must be quiet CSS-only motion and disabled through
  `prefers-reduced-motion: reduce`.

## Constraints To Preserve

- Keep the dashboard static HTML/CSS/vanilla JS for v0.3.0.
- Preserve localhost-only binding and per-process token protection.
- Do not expose private token URLs, local secrets, or personal state paths in
  committed screenshots or docs.
- Keep import as typed local path plus installed name; no drag/drop, hosted
  gallery, or upload flow in v0.3.0.
- Keep voice preview opt-in and adapter-command based.
- Keep achievements foundational and compact, with no rich celebration system.
- Keep packaged dashboard and overlay assets available through Python package
  resources.

## Later-Issue Impact

- #44 can be visual-only by replacing generic CSS variables and hard-coded
  green-tinted values with semantic tokens.
- #45 can remain HTML/CSS/JS-only if it preserves existing `data-view` buttons
  and `setView()` behavior.
- #46 can be frontend-only for built-in pet imagery, identity, XP, interactions,
  and milestones. Showing custom pet artwork would require a safe asset route or
  preview URL, so it should not be assumed.
- #47 can use existing `snapshot.job_summary` without backend changes.
- #48 can use existing job payload fields. Timestamp display is conditional
  unless `recent_jobs()` already supplies a timestamp.
- #49 can use existing API errors, `bridge.available`, empty arrays, missing
  `pet`, and `generated_at`; no backend change is required for a first pass.
- #50 and #51 are frontend-only unless testing reveals missing state labels.
- #52 should capture final screenshots after #44-#51, with token and local path
  exposure checked before committing any image.
- #53 should use the final #52 screenshot or explicitly document why screenshot
  capture was deferred.
- #54 is optional stretch and should ship only if it is low-risk, CSS-only, and
  reduced-motion safe.

## Verification

- Static source audit completed.
- Milestone issue acceptance criteria reviewed with GitHub CLI.
- Relevant release commands identified in `RELEASE_CHECKLIST.md`:
  `pytest`, `node scripts/smoke-renderer.js`,
  `scripts/smoke-hermes-pet.sh --temp-state`,
  `scripts/verify-packaged-overlay.sh`, and
  `python3 scripts/verify-package-artifacts.py`.
