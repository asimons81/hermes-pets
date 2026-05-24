# Hermes Pets landing page

This directory contains the static one-pager for `pets.tonysimons.dev`.

## Local preview

```bash
cd site
python3 -m http.server 4173
```

Then open:

```text
http://127.0.0.1:4173
```

## Deployment notes for pets.tonysimons.dev

Recommended hosting target: Vercel or any static host.

### Vercel setup

- Project root: `site/`
- Framework preset: `Other`
- Build command: none, static files only
- Output directory: `.`
- No environment variables or secrets required

### DNS

Point the subdomain at Vercel:

```text
CNAME pets -> cname.vercel-dns.com
```

## Asset sources used here

The page uses copied repo assets from:

- `docs/assets/`
- `docs/custom-pets/`
- `src/hermes_pet/overlay/assets/sprites/`

These are real product screenshots and real pet assets from the repository, not mockups.
