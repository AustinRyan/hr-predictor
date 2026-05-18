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
│   ├── landing/          # server components (Nav, Hero, Slate, Scoreboard, Arc, How, ModelAudit, Handoff, Footer)
│   └── rankings/
│       └── RankingsApp.tsx  # client component — filters + evidence-led board + parlay rail
├── lib/
│   ├── pick-view.ts      # display types + MLB headshot helper used by real picks
│   ├── ranking-sort.ts   # shared leaderboard filtering/sorting helpers
│   └── mock-data.ts      # legacy design fixtures only; not used as runtime fallback
├── scripts/
│   ├── verify-ranking-sort.mjs       # tiny Node check for board sort behavior
│   ├── verify-model-history-charts.mjs
│   └── verify-history-table-style.mjs # style contract for settled-picks table
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
- **Landing model audit entry:** homepage includes a `ModelAudit` band that
  links directly to `/model` and surfaces the active model version/test Brier
  beside the main board flow.
- **Pick history:** `/model` shows recent top-pick history from settled
  Statcast outcomes: top N picks per completed day, hit/miss, saved odds
  when available, and flat one-unit profit/loss. It also renders audit
  charts for expected-vs-actual hits by day, cumulative units, and rank-band
  calibration, plus a client-side day filter for viewing each settled day's
  top 20 and daily unit total. This uses full-game HR actuals, matching the
  promoted full-game model target, and `/model` is dynamic so refresh-script
  updates are visible on reload.
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
  snapshots. The server query mirrors the API's 1+ HR / Over 0.5 odds
  filter and rejects alternate ladder rows such as `2+ Home Runs`.
  When odds are missing, the adapter falls back to the old
  model-vs-baseline lift so the UI remains populated. Selecting the
  `MODEL LIFT` sort filters the board to rows with real sportsbook odds
  (`Pick.bookOdds`); use probability or E[HR] sorts for the full slate.
- Player display names come from the `players` dimension first, with a
  sportsbook `odds_snapshots.player_name` fallback in picks, history, and
  matchup queries. New daily refreshes should fill rookie/call-up names at
  ingestion time via MLB StatsAPI boxscore player refs.
- Equal displayed probabilities are expected with isotonic calibration.
  The board uses `PickSummary.model_rank_score` as a deterministic raw-score
  tie-breaker and shows it as `RAW` under `P(HR)` so tied calibrated buckets
  still have a visible ordering signal. Use `lib/probability-format.ts` for
  board-facing probability text; headline HR probabilities render to three
  decimals rather than the earlier one-decimal display.
- Full-game model fields flow through `PickSummary -> picks.ts -> adapters.ts`.
  The evidence drawer shows `FULL` and `START` probabilities in the `MODEL`
  group when available, plus a dedicated `BULLPEN` group from `opp_bp_*`
  values (`HR/PA`, barrel%, hard-hit%, handed split, recent load). Keep this
  display nullable-safe because old predictions and starter-only artifacts
  will not have every full-game key.
- The model page mirrors backend metric/history semantics without calling
  FastAPI. Rolling live metrics and pick history settle via
  `statcast_pitches.events = 'home_run'` anywhere in the game, not
  `matchup_features.hr_on_pa`. The settled-picks table has a lightweight
  style contract in `npm run test:history-table-style`; keep its desktop
  column widths and mobile card transformation intact when adding fields.
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
npm run test:model-charts
npm run test:history-table-style
npm run test:nav-history
npm run remotion # Remotion Studio on :3001
npm run render:promo
```
