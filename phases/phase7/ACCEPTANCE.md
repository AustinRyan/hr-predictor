# Phase 7 — Acceptance Checklist

Walked on 2026-04-23 against `ui/` built in the same session.

## Build + dev
- [x] `cd ui && npm install` clean — 360 deps, 0 vulns
- [x] `npm run dev` starts on :3000 clean — Ready in ~160ms
- [x] `npm run build` clean — all 5 routes compile
- [x] `npm run lint` clean — ESLint 0 errors
- [x] TypeScript strict — no `any` outside narrow third-party gaps

## Stage 1 — visual parity (no motion)
- [x] Nav: clay ◆ + HOMERUN wordmark + mono sub + pulsing live dot
- [x] Hero: giant "CALL YOUR SHOT." display with clay period + eyebrow + lede + CTAs
- [x] Hero pick card: portrait w/ duotone headshot + grid + noise + live pill + player identity + prob big + 4-stat grid
- [x] Slate horizontal scroller renders 13 game cards (scroll-snap)
- [x] Scoreboard LED grid (8 games) + bottom stats row (1,412 / 7.3 / 0.0043 / 162)
- [x] How: INGEST / MODEL / GRADE 3-step with step lists
- [x] Handoff: "THE SLATE IS LIVE." title + accent line separator
- [x] Ticker animates via CSS keyframes (the only Stage 1 motion)
- [x] Grain + scanlines + vignette overlays visible

## Stage 2 — motion
- [x] Boot radar sweep plays on first paint; fills progress bar; fades after ~1s
- [x] Arc ball visibly arcs on scroll over a 400vh stage (sticky pin)
- [x] Ghost trail (10-slot ring buffer) fades behind ball
- [x] Ground shadow ellipse scales + fades with altitude
- [x] Batter silhouette swings at progress 0-0.05 with contact-flash
- [x] Damage numbers eject from ball's current position at each threshold (EV/LA/WIND/PARK/CARRY)
- [x] Physics warp: ball dwells near apex, accelerates on descent
- [x] Stadium-lights flicker + crowd silhouette rises + finale P(HR) count-up at progress > 0.88
- [x] Inning chyron slides in from the left on section entry
- [x] HR easter egg: type `H` then `R` anywhere → ball launches + "HOME RUN" flash
- [x] `prefers-reduced-motion: reduce` hides boot, collapses arc stage to a static panel, disables chyron

## Stage 3 — rankings + parlay
- [x] Sort buttons (Probability / E[HR] / Book edge) — active state cycles
- [x] Min P(HR) slider updates filter live; slider-val shows `X.X%`
- [x] Team dropdown filters; ALL · 30 TEAMS option
- [x] Show 10/20/50 limit toggles
- [x] Click `+` on a row → adds to parlay rail; button flips to ✓
- [x] Parlay rail shows legs, combined P, fair American odds, $100-pays
- [x] LOCK PARLAY button disabled with <2 legs; enabled from 2+
- [x] Locking flips the rail to cream-paper ticket with perforations, LOCKED stamp, barcode
- [x] SHARE button canvas-renders ticket to PNG; Web Share API on supported browsers, download fallback elsewhere
- [x] "tear up ticket" returns to rankings mode, clears legs

## Stage 4 — real data wiring
- [x] `ui/lib/api.ts` typed client hits `${NEXT_PUBLIC_API_URL}/...` (defaults `http://localhost:8765`)
- [x] Home page fetches `/picks/today?limit=50`; if API returns non-empty, data flows through `adaptPicksList` into Hero + RankingsApp
- [x] Graceful fallback: API unreachable, 4xx, malformed JSON, or empty response → mock `PICKS` used
- [x] ISR: `/` and `/model` revalidate every 5 min (matches backend Redis TTL)

## Stage 5 — detail pages
- [x] `/player/{mlbamId}` renders player profile, rolling 30d card grid, season card grid, today's prediction card with link to matchup
- [x] `/matchup/{gamePk}/{batterId}` renders hero ("BATTER vs PITCHER @ PARK"), P(≥1 HR) / P(≥2 HR) / E[HR] / model card, top-10 SHAP horizontal bars, batter + pitcher + context grids
- [x] `/model` renders training metadata header, training metrics grid, reliability SVG chart (falls back to empty-state panel when no outcomes), rolling-live grid
- [x] Unknown player/matchup IDs → styled `/not-found` page with clay accent ("OFF THE BAT. FOUL BALL.")

## Live backend sanity
- [x] `/health` → 200 with model_version v20260423_231941 (current PRODUCTION)
- [x] `curl /player/660271` → full JSON with Ohtani profile + rolling + today's prediction
- [x] `curl /matchup/823233/660271` → game + batter + pitcher + park + weather + prediction
- [x] All 5 Next.js routes: `/`, `/model`, `/player/660271`, `/matchup/823233/660271` → HTTP 200 when backend up
- [x] `/does-not-exist` → HTTP 404 via styled not-found page

## Accessibility
- [x] Every interactive element is keyboard-reachable (nav, filters, add-to-parlay, LOCK, SHARE, links)
- [x] Focus rings visible on interactive elements (browser defaults preserved; clay hover states layered on top)
- [x] Probability signaled BOTH visually (bar width) AND textually (percentage tabular nums)
- [x] Every animated element has a `prefers-reduced-motion: reduce` opt-out
- [x] `aria-hidden="true"` on all purely decorative SVG/DOM (grain, scanlines, overlays, arc SVG, chyron)
