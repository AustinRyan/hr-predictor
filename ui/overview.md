# ui/ — Homerun frontend

**Purpose:** Next.js 15 App Router frontend for the HR Predictor. Implements the stadium-brutalist design from `phases/phase7/design-source/project/Homerun.html`.

See `phases/phase7/PROMPT.md` for the full phased scope. This file describes the code layout and conventions.

## Stack
- Next.js 16.2 (App Router) + React 19 + TypeScript strict
- Tailwind v4 (utility layer only — design tokens stay as CSS custom properties)
- `next/font/google`: Barlow Condensed (display), Archivo (body), JetBrains Mono (data/labels)
- `lucide-react` for icons (planned use in Stage 3+)

## Layout
```
ui/
├── app/
│   ├── layout.tsx        # fonts, grain/scanlines/vignette overlays, <html data-accent data-intensity>
│   ├── page.tsx          # composes landing sections
│   └── globals.css       # ported design tokens + section styles (~900 lines)
├── components/
│   ├── landing/          # server components (Nav, Hero, Slate, Scoreboard, ArcPlaceholder, How, Handoff, Footer)
│   └── rankings/
│       └── RankingsApp.tsx  # client component — filters + parlay rail
└── lib/
    └── mock-data.ts      # typed PICKS/SCOREBOARD/SLATE_CARDS/TICKER (Stage 4 replaces w/ real API)
```

## Design tokens — DO NOT refactor into Tailwind theme
All tokens live as CSS custom properties in `globals.css` under `:root` and `[data-accent="..."]` / `[data-intensity="..."]` variants. The runtime tweaks panel (Stage 3+) flips `data-accent` on `<html>` to retheme the whole surface. Hoisting these into `tailwind.config` would break that mechanism.

## Stage progress
- **Stage 1 (now):** scaffold + static landing w/ mock data, no scroll animation yet.
- **Stage 2:** scroll-linked signature arc, chyrons, loading ritual, HR easter egg.
- **Stage 3:** parlay lock/ticket flip + share-as-image.
- **Stage 4:** wire rankings + hero #1 to `/picks/today` via `NEXT_PUBLIC_API_URL`.
- **Stage 5:** `/player/[id]`, `/matchup/[gamePk]/[batterId]`, `/model` pages in same aesthetic.

## Conventions
- Server components by default. `'use client'` only when interactivity (refs/state) is required.
- No `any`. Any third-party gap uses `unknown` + narrow.
- Tabular numerics on every displayed number (`font-variant-numeric: tabular-nums`).
- All probability UI uses both a bar AND text, never color alone.
- MLB headshots via `https://img.mlbstatic.com/mlb-photos/image/upload/w_426,q_auto/v1/people/{id}/headshot/67/current`; use native `<img>` with `eslint-disable-next-line @next/next/no-img-element` (not `<Image>`) so duotone CSS filters compose cleanly.

## Commands
```
cd ui
npm run dev      # :3000
npm run build    # prod build
npm run lint     # eslint
```
