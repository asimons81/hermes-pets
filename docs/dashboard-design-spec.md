# Hermes Pets Dashboard Design Spec

The v0.3.0 dashboard is premium local operator software: dense, calm, tactile, and specific to Hermes Pets. It opens directly into the working console, not a landing page. Every viewport must keep controls readable, stable, and non-overlapping.

## Information Architecture

- Overview: pet state, selected custom pet, bridge status, recent jobs, recent events, and achievement preview.
- Custom pets: installed pet list, valid/current/invalid states, typed local path import, select, remove, and overlay test action.
- Preferences: notification profile segmented control, quiet mode segmented control, tray/idle toggles, and numeric bubble throttle.
- Voice: opt-in preview toggle, adapter command, explicit test text, and last result.
- Achievements: compact locked/unlocked ledger only.

## Visual System

- Layout uses a persistent left rail on desktop and a compact top rail on narrow screens.
- Panels use 8px radius or less, restrained borders, and scan-friendly headings. Avoid nested cards.
- Typography stays dashboard-sized: compact section heads, short labels, and no hero-scale marketing copy.
- Palette is dark neutral with green and blue operational accents. Warning and error states use distinct amber/red tones.
- Empty states must explain the local state condition and the next concrete operator action.

## Design Tokens

Dashboard CSS uses semantic custom properties rather than component-only color literals. The base token set covers:

- Backgrounds: canvas, rail, surface, raised surface, subtle surface, row, and input.
- Borders: subtle, default, and strong.
- Text: primary, secondary, and muted.
- Signals: primary aqua accent, secondary blue accent, companion warmth, success, warning, danger, and focus ring.
- System primitives: compact spacing scale, 6px/8px radius scale, pill radius, panel shadow, and brand shadow.
- Component aliases: panel, controls, empty states, and alert tones.

Green is reserved for success or specific active-state meaning. The default dashboard read should be neutral charcoal with warm off-white text, controlled aqua product signal, restrained amber warmth, and state colors only where they communicate status.

## Controls

- Booleans use toggles/checkboxes.
- Profile-like choices use segmented controls.
- Numeric values use number inputs.
- Buttons are reserved for commands: refresh, test event, import, select, remove, save, and test voice.

## Required States

- Overview: loading, empty pet state, populated pet state, recent activity present, and API error banner.
- Custom pets: zero pets, one pet, many pets, invalid installed pet, current pet removal, duplicate import error.
- Preferences: saved, invalid value rejection, bridge offline while prefs still save.
- Voice: disabled default, enabled with command, missing command, failing command, explicit test result.
- Achievements: all locked, some unlocked, new unlock event.

## Anti-Slop Rules

- No marketing hero, decorative product pitch, oversized headline, or generic admin template layout.
- No low-contrast placeholder text.
- No clipped button/control text.
- No overlapping controls at desktop or narrow/mobile widths.
- No blank panels without intentional empty states.
- No drag/drop custom pet import in v0.3.0.
