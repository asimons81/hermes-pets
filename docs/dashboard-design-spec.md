# Hermes Pets Dashboard Design Spec

The v0.3.0 dashboard is premium local operator software: dense, calm, tactile, and specific to Hermes Pets. It opens directly into the working console, not a landing page. Every viewport must keep controls readable, stable, and non-overlapping.

## Information Architecture

- Overview: pet state, selected custom pet, bridge status, recent jobs, recent events, and achievement preview.
- Custom pets: installed pet list, valid/current/invalid states, typed local path import, select, remove, and overlay test action.
- Preferences: notification profile segmented control, quiet mode segmented control, tray/idle toggles, and numeric bubble throttle.
- Voice: opt-in preview toggle, adapter command, explicit test text, and last result.
- Achievements: compact locked/unlocked ledger only.

## Pet Changing Semantics

The dashboard has three related but separate pieces of pet state:

- Active pet identity and progression live in `pet.json`. This is the canonical companion record: name, species, variant, hat, XP, level, stats, interactions, milestones, and creation timestamps.
- Built-in species sprites are the packaged visual set for the active pet species. They are selected by replacing the canonical active pet with a fresh hatch.
- Custom pet packages live under the local custom-pets directory. Activating one writes it as the canonical active pet in `pet.json` with species `custom`, while `custom-pet-current.json` points the overlay at the installed sprite package.

Changing to a built-in species from the dashboard means creating and saving a fresh `Pet` in `pet.json`, matching `hermes-pet hatch` reset semantics. The new companion starts over with fresh XP, stats, interactions, milestones, variant, hat, and timestamps. Choosing a specific built-in species uses that species for the fresh pet. Random hatch uses the normal gacha pool.

Choosing a built-in species or random hatch also clears `custom-pet-current.json` so the visible pet matches the newly active built-in species. Installed custom pet package directories are kept. Clearing the current custom pet selection keeps installed packages on disk and clears the custom-only active pet state when applicable.

Replacement confirmation copy should be direct and consistent:

> Changing pets creates a fresh companion and resets XP, stats, and milestones. Installed custom pet packages are kept, but the current custom sprite selection will be cleared.

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
