# Phase 7 — Next.js Frontend (Design-Driven Rewrite)

**Supersedes:** the original PROMPT.md draft (restrained shadcn/ui dashboard). The user handed off a finished Claude Design bundle — stadium brutalist landing + rankings app — and that is the canonical design. The shadcn-flavored spec is explicitly abandoned.

## Required reading
1. `./CLAUDE.md`
2. `./abstract.md` — Phases 0–6 complete; Phase 7 is the first frontend work.
3. `./src/api/overview.md` — API reference (endpoints, response shapes).
4. `phases/phase7/design-source/README.md` — Claude Design handoff notes.
5. `phases/phase7/design-source/chats/chat1.md` — the full iteration log between user and design assistant. **The transcripts capture intent; don't skip.**
6. `phases/phase7/design-source/project/Homerun.html` — the canonical single-file prototype (inline CSS + JS).

`app.js`, `styles.css`, `data.js` in the same folder are **orphaned pre-inline originals** per the chat transcript — reference only; `Homerun.html` is ground truth.

---

## Objective
Port the `Homerun.html` stadium-brutalist landing + rankings app into a Next.js 15 App Router app under `ui/`. Visual output must match the prototype; internal structure is ours (React components, not the prototype's vanilla-JS DOM manipulation).

**Scope boundary:** Frontend only. No backend changes.

## Aesthetic / non-negotiable design DNA
- **Palette:** navy-night background (`#07080c` → `#121725`) + infield-clay accent (`#ff5a1f` default, with emerald/amber/cyan variants wired as `data-accent` on `<html>`).
- **Type:** Barlow Condensed (display, 400-900), Archivo (body, 400-900), JetBrains Mono (data/labels, 400-700), Bebas Neue (fallback display). All via `next/font/google`.
- **Global overlays:** fixed `grain`, `scanlines`, `vignette` layers at z-index 60–62; `data-intensity` attribute on `<html>` controls grain/scan opacity (`calm` / `mid` / `max`).
- **Scale:** display type clamped `clamp(88px, 14vw, 240px)`; section titles `clamp(56px, 9vw, 140px)`. Tabular numerics everywhere numbers appear.
- **Motion vocabulary:** `cubic-bezier(.2,.8,.2,1)` and `cubic-bezier(.7,0,.2,1)` as `--ease` / `--ease-bold`.

---

## Delivery plan — phased

Execution is staged so we have checkpoints; each stage ships something working:

### Stage 1 — Scaffold + static landing (visual parity, no motion)
- Next.js 15 / React 19 / TypeScript strict / Tailwind CSS at `ui/`.
- `next/font/google` loaders for the four families.
- `app/globals.css` carries the ported CSS custom properties + overlay layers.
- Mock data ported from `data.js` to `ui/lib/mock-data.ts` (typed).
- Components (server, no `'use client'` unless interactive):
  - `components/landing/Nav.tsx`
  - `components/landing/Hero.tsx` (eyebrow, display title, lede, CTAs, pick card with real MLB headshot + duotone, ticker strip)
  - `components/landing/Slate.tsx` (horizontal scroller of today's 15 games — static for now; snap scroll only)
  - `components/landing/Scoreboard.tsx` (LED grid across all games + bottom stats row)
  - `components/landing/How.tsx` (INGEST / MODEL / GRADE three-step)
  - `components/landing/Handoff.tsx`
  - `components/landing/ArcPlaceholder.tsx` — just a section shell with heading + empty sticky stage. Stage 2 fills in.
  - `components/rankings/RankingsApp.tsx` (table + parlay rail; static sort/filter wired as client)
- `app/page.tsx` composes them.
- `npm run build` + `npm run dev` clean.

### Stage 2 — Scroll signature moment
- Port the arc logic from `Homerun.html`'s final `SIGNATURE: BALL ARC` / "epic rewrite" blocks into a client component:
  - SVG ball with stitching (60–80px equivalent)
  - Ghost-trail circles
  - Ground shadow
  - Batter silhouette + swing animation + contact flash
  - Damage numbers ejecting from ball (EV / LA / WIND / PARK / P(HR))
  - Physics-timed scroll mapping (slow at apex)
- Inning chyrons (top-of-N ticker on section entry).
- Horizontal slate: scroll-linked translate while vertical scroll progresses.
- Loading ritual (radar sweep + "CALIBRATING MODEL v*..." for ~800ms).
- HR easter egg: type `H` then `R` anywhere → ball launches across viewport.

### Stage 3 — Rankings + parlay
- Sort (prob / EHR), min-prob slider, team filter, limit selector — all client-side against the same data source.
- Add-to-parlay rail with live combined-odds recompute.
- `LOCK PARLAY` → ticket flip (perforated edges, LOCKED stamp).
- Share-as-image: canvas render of ticket → PNG → Web Share API with download fallback.

### Stage 4 — Real data wiring
- `ui/lib/api.ts`: typed client for `/picks/today`, `/player/{id}`, `/matchup/{gamePk}/{batterId}`, `/model/metrics`.
- `NEXT_PUBLIC_API_URL` (defaults `http://localhost:8000`).
- Hero #1 pick + rankings table hydrate from `/picks/today`.
- Scoreboard / slate derive from same API (grouped by game_pk).
- Ticker stays authored for flair.
- Empty-state + error states match the aesthetic (no generic spinners).

### Stage 5 — Detail pages
- `/player/[id]` — hero header w/ MLB CDN duotone headshot + rolling metrics cards + today's prediction card + recent games. Rendered in the stadium brutalist voice.
- `/matchup/[gamePk]/[batterId]` — "BATTER vs PITCHER AT PARK" hero, P(≥1 HR) / E[HR] / P(≥2 HR) big numbers, feature-contribution horizontal bars (top-10 SHAP), context panel (park/weather/roof), lineup.
- `/model` — production model version, reliability chart, rolling perf (recharts), top-30 feature importance.

---

## Stack (locked)
- Next.js 15 App Router, React 19, TypeScript strict.
- Tailwind CSS (utility layer only; design tokens live in CSS custom properties, not `tailwind.config`).
- `next/font/google` for the four type families.
- `lucide-react` for icons.
- `recharts` for Stage 5 charts.
- No shadcn/ui. No component library. All components custom-built to match the design.
- No external animation library for Stage 2 — the prototype's vanilla approach (`requestAnimationFrame` + CSS) ports cleanly into `useEffect` + refs and is more reliable for scroll-linked work than Framer Motion here.

## Conventions
- **Server components by default.** `'use client'` only when interactivity or refs are required (arc, rankings filters, parlay, share).
- **No `any`.** Any unavoidable third-party type gaps use `unknown` + narrow.
- **No inline styles** except dynamic CSS custom properties (`style={{ '--w': `${prob}%` }}`).
- **Tabular numerics everywhere** numbers appear.
- **Design tokens stay in `globals.css`.** Don't rewrite them as Tailwind theme colors — the design is heavy on custom properties and `data-accent` variants.

---

## Acceptance (updated, supersedes original)

```markdown
# Phase 7 — Acceptance Checklist

## Build + dev
- [ ] `cd ui && npm install` clean
- [ ] `npm run dev` starts on :3000 clean
- [ ] `npm run build` clean
- [ ] `npm run lint` clean
- [ ] TypeScript strict — no errors

## Stage 1 — visual parity (no motion)
- [ ] Nav matches (clay mark + HOMERUN wordmark + mono sub + live dot)
- [ ] Hero: "CALL YOUR SHOT." display, clay period, pick card with duotone MLB headshot
- [ ] Slate horizontal scroller renders 15 game cards
- [ ] Scoreboard LED grid + bottom stats row ("15 / 412 / +2.0 / .0043")
- [ ] How: INGEST / MODEL / GRADE three-up
- [ ] Handoff section with "INTO THE BOARD →" button
- [ ] Rankings table with 20 rows, parlay rail on right
- [ ] Ticker animates with CSS keyframes (the only Stage 1 motion allowed)
- [ ] Grain + scanlines overlays visible

## Stage 2 — motion
- [ ] Arc: ball visibly arcs on scroll with ghost trail + ground shadow
- [ ] Batter silhouette swings at progress 0-0.05
- [ ] Damage numbers eject from ball during flight
- [ ] Loading ritual plays on first paint
- [ ] HR easter egg fires
- [ ] Inning chyrons slide in on section enter
- [ ] Respects `prefers-reduced-motion`

## Stage 3 — rankings interactive
- [ ] Sort / min-prob / team filter / limit all work
- [ ] Add-to-parlay updates combined odds + payout live
- [ ] LOCK PARLAY flips rail to ticket view
- [ ] Ticket SHARE generates PNG + invokes Web Share API (download fallback)

## Stage 4 — real data
- [ ] Hero + rankings populated from `/picks/today`
- [ ] `NEXT_PUBLIC_API_URL` respected
- [ ] Empty / error states styled in-aesthetic

## Stage 5 — detail pages
- [ ] `/player/{id}` renders w/ rolling metrics + today's prediction
- [ ] `/matchup/{gamePk}/{batterId}` renders w/ SHAP bars + context
- [ ] `/model` renders reliability chart + rolling perf
- [ ] 404 styled in-aesthetic

## Accessibility
- [ ] Every interactive element keyboard-reachable
- [ ] Focus rings visible on clay buttons + table rows
- [ ] Probability signaled visually AND textually
- [ ] `prefers-reduced-motion` disables arc animation
- [ ] Lighthouse A11y ≥ 95 on `/`
```

---

## STOP conditions
- Do NOT start Phase 8 (LangGraph agent) until all five stages ship and the user signs off.
- Do NOT add shadcn/ui, chakra, mui, or any component library mid-build.
- Do NOT rewrite design tokens as Tailwind `theme.extend.colors` — they stay as CSS custom properties so the `data-accent` / `data-intensity` runtime-switcher works.
