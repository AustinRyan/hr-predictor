# Phase 7 — Next.js Frontend

## Required reading
1. `./CLAUDE.md`
2. `./MASTER_PLAN.md` — Phase 7 section
3. `./abstract.md` — Phases 0–6 complete
4. `./src/api/overview.md` — API reference

---

## Objective
Ship a polished, prop-bet-focused UI. Daily rankings are the hero. Player and matchup pages for drill-down. Model performance dashboard for transparency.

**Scope boundary:** Frontend only. No backend changes. No auth (v1 is local/personal).

---

## Deliverables

### 1. Project scaffold

Create `ui/` at repo root using Next.js 15 with App Router:

```
ui/
├── overview.md
├── package.json
├── tsconfig.json
├── next.config.mjs
├── tailwind.config.ts
├── postcss.config.mjs
├── .eslintrc.json
├── app/
│   ├── layout.tsx
│   ├── page.tsx                  # rankings (home)
│   ├── player/[id]/page.tsx
│   ├── matchup/[gamePk]/[batterId]/page.tsx
│   ├── model/page.tsx
│   ├── api/                      # Next route handlers if needed
│   └── globals.css
├── components/
│   ├── ui/                       # shadcn/ui primitives (added via CLI)
│   ├── picks/
│   │   ├── PicksTable.tsx
│   │   ├── PickRow.tsx
│   │   └── PicksFilters.tsx
│   ├── player/
│   │   ├── PlayerHeader.tsx
│   │   ├── RollingMetrics.tsx
│   │   └── RecentGamesChart.tsx
│   ├── matchup/
│   │   ├── MatchupHero.tsx
│   │   ├── FeatureContributions.tsx
│   │   └── PASequence.tsx
│   ├── model/
│   │   ├── ReliabilityChart.tsx
│   │   └── RollingMetricsChart.tsx
│   └── common/
│       ├── ProbabilityBar.tsx
│       ├── TeamBadge.tsx
│       └── WeatherBadge.tsx
├── lib/
│   ├── api.ts                    # typed API client
│   ├── types.ts                  # mirrors backend Pydantic models
│   ├── format.ts                 # percentage, odds, etc.
│   └── fetcher.ts                # SWR or fetch utilities
└── public/
```

Stack:
- Next.js 15 (App Router, React 19)
- Tailwind CSS
- shadcn/ui (install via `npx shadcn@latest init` and `add button card table badge dialog tabs skeleton select input`)
- `recharts` for charts
- `lucide-react` for icons
- TypeScript strict mode

Dark mode: default dark, `next-themes` with system preference respect.

### 2. API client (`ui/lib/api.ts`)

Thin typed wrapper around fetch:

```typescript
// ui/lib/types.ts
export interface PickSummary { ... }
export interface PlayerDetail { ... }
export interface MatchupBreakdown { ... }
export interface ModelMetrics { ... }

// ui/lib/api.ts
export async function getPicksToday(params: {
  limit?: number;
  minProb?: number;
  team?: string;
  sort?: 'prob' | 'expected_hrs';
}): Promise<PickSummary[]>

export async function getPlayer(mlbamId: number): Promise<PlayerDetail>

export async function getMatchup(gamePk: number, batterId: number): Promise<MatchupBreakdown>

export async function getModelMetrics(): Promise<ModelMetrics>
```

Environment: `NEXT_PUBLIC_API_URL` in `.env.local`; defaults to `http://localhost:8000`.

Server-side calls from RSCs use direct server fetch; client components use the same functions via SWR or plain fetch.

### 3. Pages

#### `/` (home — rankings dashboard)

Hero section: "Today's Top Home Run Picks — [Date]". Show total games today, model version in small text.

Main table (`PicksTable`):
- Columns: Rank | Player (team badge) | Matchup (vs pitcher, park, weather icon) | Probability (visual bar + %) | Expected HRs | Actions
- Sortable by probability or expected_hrs
- Filters: team selector, min probability slider (default 5%), limit (10/20/50)
- Click row → navigate to `/matchup/{gamePk}/{batterId}`
- Loading: skeleton rows
- Empty state: "No games today" or "No picks match your filters"

Secondary panel: current model version + live metrics summary (link to `/model`).

Design notes:
- Probability bar: green gradient, wider = higher. Visual before textual.
- Weather badge: icon + temperature + wind indicator (arrow showing direction relative to park)
- Mobile: table collapses to stacked cards at < 768px

#### `/player/[id]`

- Hero: Name, team, position, handedness, headshot (use `https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_213,q_auto:best/v1/people/{mlbam_id}/headshot/67/current` — public MLB CDN)
- Rolling metrics card: barrel %, xwOBA, avg EV for 7d/14d/30d/season (use rechart line charts)
- Today's prediction card (if playing today) — links to matchup detail
- Recent games table: last 10 games with basic batting line

#### `/matchup/[gamePk]/[batterId]`

- Hero: "Batter vs Pitcher at Park"
- Key numbers: P(≥1 HR), E[HR], P(≥2 HR)
- PA sequence visualization: for each projected PA (1st, 2nd, 3rd, 4th+ bullpen), show the per-PA probability as a bar
- Feature contributions: top-10 SHAP values as horizontal bar chart (positive red/up, negative blue/down)
- Context panel: park factor, weather (temp, wind vector visual), roof status
- Lineup: show batting order context

#### `/model`

- Header: production model version, training date range, training metrics
- Reliability chart: binned predicted probability vs actual rate (ideal = diagonal)
- Rolling performance chart: log loss and Brier score over last 30 days
- Calibration table: bin-by-bin numbers
- Feature importance (top 30 SHAP)

### 4. Common components

#### `ProbabilityBar` (`components/common/ProbabilityBar.tsx`)
Horizontal bar with smooth green gradient. Width = probability × 100 * some multiplier. Shows percentage text on the bar. Accessible (aria-valuenow, etc.).

#### `WeatherBadge`
Compact component: temp + wind icon. Tooltip on hover shows full weather. Icon rotates based on wind direction.

#### `TeamBadge`
Just a styled pill with team abbr + color-coded background.

### 5. Data fetching strategy

- Home page (`/`): server component; fetch on each request (5-min backend cache handles load)
- Player page: server component; player data doesn't change intra-day
- Matchup page: server component; always fresh
- Model page: server component; revalidate every 15 min

Use `revalidate: 300` on `fetch` calls for the home page.

### 6. Styling conventions

- Tailwind utility-first
- Dark palette: zinc-950 background, zinc-100 text, accent green (emerald-500) for good picks, rose-500 for warnings
- Typography: sans-serif system stack; tabular-nums on all probability cells
- Consistent card pattern: `rounded-lg border border-zinc-800 bg-zinc-950 p-4`
- Spacing: 4/6/8 scale; favor generous whitespace

### 7. Accessibility & polish

- Every interactive element keyboard-accessible
- Focus rings visible
- Color not the only signal (probability has both bar width AND text)
- Skeleton loaders during fetch
- Error boundary at the layout level with a friendly message + retry

### 8. Phase docs

- `phases/phase7/ACCEPTANCE.md`
- `phases/phase7/NOTES.md`
- Populate `ui/overview.md` with architecture, data-fetching patterns, and how to add a page

---

## Acceptance checklist

```markdown
# Phase 7 — Acceptance Checklist

## Build & dev
- [ ] `cd ui && npm install` completes without error
- [ ] `npm run dev` starts on :3000 without warnings
- [ ] `npm run build` produces a clean production build
- [ ] `npm run lint` passes clean
- [ ] No TypeScript errors in strict mode

## Pages render
- [ ] `/` shows today's top picks with probability bars
- [ ] Clicking a pick navigates to `/matchup/...` with no full-page reload
- [ ] `/player/{known_id}` renders player profile with rolling metrics
- [ ] `/model` renders reliability curve and rolling metrics
- [ ] 404 page shows for unknown player

## Interactivity
- [ ] Sort by probability and by expected HRs both work
- [ ] Team filter narrows correctly
- [ ] Min-probability slider filters live
- [ ] Limit selector changes row count

## Visual quality
- [ ] Dark mode looks polished on /, /player/*, /matchup/*, /model
- [ ] Mobile responsive: table becomes stacked cards < 768px
- [ ] Weather badge shows direction visually, not just a number
- [ ] Probability bars are immediately scannable (visual first, text second)

## Performance
- [ ] Home page first contentful paint < 1.5s on local dev
- [ ] Lighthouse score (desktop): Performance ≥ 85, Accessibility ≥ 95
- [ ] No large hydration errors in console

## Docs
- [ ] `ui/overview.md` explains data flow, conventions, how to extend
- [ ] `abstract.md` shows Phase 7 complete
```

---

## Non-negotiables

- **TypeScript strict mode.** `any` is banned except for third-party types we can't control.
- **Server components by default.** Only use `'use client'` when you need interactivity.
- **Mirror backend types exactly.** If backend Pydantic schema changes, update `ui/lib/types.ts` first.
- **No inline styles.** Tailwind or component-level classes.
- **No hardcoded API URL.** Use `NEXT_PUBLIC_API_URL`.
- **Accessibility is not optional.** Tab through every page before calling it done.

---

## Post-phase ritual

1. `npm run build` → success
2. `npm run lint` → clean
3. Walk acceptance checklist
4. Visual review: every page in dark mode + light mode + mobile width
5. Update docs
6. Commit + tag `phase-7-complete`

---

## STOP condition

Do not start Phase 8 (LangGraph agent) without approval. Report:
1. Lighthouse scores
2. Screenshots of /, /player/*, /matchup/*, /model
3. Any UX tradeoffs made
