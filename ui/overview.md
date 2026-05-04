# ui/ — Homerun frontend

**Purpose:** Next.js 16.2 App Router frontend for the HR Predictor. Implements the stadium-brutalist design from `phases/phase7/design-source/project/Homerun.html`.

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
│       └── RankingsApp.tsx  # client component — filters + evidence-led board + parlay rail
├── lib/
│   ├── pick-view.ts      # display types + MLB headshot helper used by real picks
│   ├── ranking-sort.ts   # shared leaderboard filtering/sorting helpers
│   └── mock-data.ts      # legacy design fixtures only; not used as runtime fallback
├── scripts/
│   └── verify-ranking-sort.mjs  # tiny Node check for board sort behavior
└── remotion/             # renderable promotional video compositions
```

## Design tokens — DO NOT refactor into Tailwind theme
All tokens live as CSS custom properties in `globals.css` under `:root` and `[data-accent="..."]` / `[data-intensity="..."]` variants. The runtime tweaks panel (Stage 3+) flips `data-accent` on `<html>` to retheme the whole surface. Hoisting these into `tailwind.config` would break that mechanism.

## Stage progress
- **Stage 1:** scaffold + static landing from the original design bundle.
- **Stage 2:** scroll-linked signature arc, chyrons, loading ritual, HR easter egg.
- **Stage 3:** parlay lock/ticket flip + share-as-image.
- **Stage 4:** wire rankings + hero #1 to live predictions. The app now
  queries Neon directly from server code, filters to one active model version
  for the latest slate, uses MLB Eastern date for "today", and displays
  real PropLine odds edge when `odds_snapshots` has matching rows. The
  visible homepage no longer falls back to mock picks; query failures or
  empty slates render explicit empty states.
- **Stage 5:** `/player/[id]`, `/matchup/[gamePk]/[batterId]`, `/model` pages in same aesthetic.
- **Mobile hardening:** coarse-pointer/small-screen devices render a compact
  static arc card instead of the full scroll-physics arc. Leaderboard sort
  behavior lives in `lib/ranking-sort.ts` and is covered by
  `npm run test:ranking-sort`; mobile rows keep visible rank pills so sort
  changes are obvious. Team filters use batter-team abbreviations inferred
  from lineup rows, not just home/away game abbreviations.

## Conventions
- Server components by default. `'use client'` only when interactivity (refs/state) is required.
- No `any`. Any third-party gap uses `unknown` + narrow.
- Tabular numerics on every displayed number (`font-variant-numeric: tabular-nums`).
- All probability UI uses both a bar AND text, never color alone.
- The leaderboard keeps one dominant score column, shows four compact
  factor signals by default, and puts the full `BAT`, `MATCH`, `PARK/WX`,
  and `MODEL` factor set inside the expandable evidence drawer. Keep new
  leaderboard data in `PickSummary -> adapter -> Pick.factors`; avoid adding
  more standalone columns unless the factor needs to drive sorting.
- Real betting edge is `PickSummary.model_edge` from persisted odds
  snapshots. When odds are missing, the adapter falls back to the old
  model-vs-baseline lift so the UI remains populated.
- Mobile filter controls should remain touch-sized (44px minimum) and the
  `MODEL LIFT` sort must continue using `sortPicksForBoard` rather than
  duplicating ad hoc comparator logic in the component.
- MLB headshots via `https://img.mlbstatic.com/mlb-photos/image/upload/w_426,q_auto/v1/people/{id}/headshot/67/current`; use native `<img>` with `eslint-disable-next-line @next/next/no-img-element` (not `<Image>`) so duotone CSS filters compose cleanly.

## Commands
```
cd ui
npm run dev      # :3000
npm run build    # prod build
npm run lint     # eslint
npm run test:ranking-sort
npm run remotion # Remotion Studio on :3001
npm run render:promo
```
