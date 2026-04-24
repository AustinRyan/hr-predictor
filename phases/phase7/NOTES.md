# Phase 7 — Notes

## Design source is canonical

`phases/phase7/design-source/project/Homerun.html` is a self-contained HTML file with inline CSS + JS. The sibling `app.js` / `styles.css` / `data.js` are orphaned pre-inline scaffolding (confirmed in the chat transcript) — don't rely on them. When porting CSS or JS logic, read from the inlined block in `Homerun.html`.

## PROMPT.md was rewritten mid-phase

The original Phase 7 PROMPT specced a restrained shadcn/ui dark dashboard. The user handed off a finished Claude Design bundle (stadium brutalist + scroll-linked arc + duotone + parlay ticket) that was substantially different in voice and scope. PROMPT.md was rewritten in commit [see git log] to reflect the design-driven 5-stage plan. The original shadcn-flavored version is abandoned.

## CSS custom properties over Tailwind theme

Design tokens live in `globals.css` under `:root` + `[data-accent="..."]` / `[data-intensity="..."]` variants. They are NOT hoisted into `tailwind.config` (Tailwind v4 `@theme`). Reason: the tweaks panel (Stage 3+) flips `data-accent` on `<html>` at runtime to retheme the whole surface. Hoisting to the Tailwind theme would freeze the accent at build time.

Tailwind v4 is still installed and available via `@import "tailwindcss"`, but the design is heavy on custom CSS-class components. The only Tailwind utilities used in practice are `class="flex"` / `gap` / layout helpers in a few spots.

## Scroll-linked ball arc: refs + rAF, not React state

The arc (`components/landing/Arc.tsx`) runs a scroll listener + rAF loop that mutates SVG attributes directly via refs. Using React state for the ball position would trigger reconciliation on every scroll pixel and tank perf. The same pattern is used for the ghost trail (innerHTML re-render) and damage numbers (ad-hoc DOM create + `setTimeout` cleanup).

One subtle gotcha: the `blur stdDeviation` and trail rendering both depend on `path.getTotalLength()` which is only computed after the `<path>` has been laid out by the browser. The `useEffect` inits once on mount when the DOM is ready, so this is fine; if we ever render the arc hidden-then-shown we'd need a `ResizeObserver` to re-measure.

## Physics warp

The linear scroll progress is remapped through `physicsWarp(p)` before sampling the SVG path. Real home-run trajectories spend ~60% of their air-time in the upper half, so the warp is ease-out on ascent and ease-in on descent, split at p=0.5. Visually the ball "hangs" at apex the way a real HR does before dropping.

The path dashoffset uses the RAW progress so the trajectory draws continuously with scroll; only the ball's position on the path uses the warped progress.

## Ticket share-as-image: hand-rolled canvas, not html2canvas

`Ticket.tsx` implements `renderTicketToPng` by drawing the ticket directly into a `<canvas>` at device-pixel resolution. html2canvas was considered and rejected:
- CSS custom properties don't always resolve correctly inside html2canvas at clone time
- the perforated-edge radial-gradient background-image fought with the library's DOM-to-canvas pass
- we need the output to look consistent across iOS Safari, Chrome, Firefox; hand-rolling guarantees pixel fidelity

The Web Share API is used when `navigator.canShare({ files })` returns true (Safari iOS ≥ 15, Chrome Android). Elsewhere it falls back to `<a download>`. No server-side rendering needed.

## API fallback strategy

`lib/api.ts` returns `T | null` on any failure (network, non-2xx, parse). `app/page.tsx` then does:

```ts
const api = await getPicksToday({ limit: 50 });
const picks = api && api.length > 0 ? adaptPicksList(api) : undefined;
```

If `picks` is undefined, Hero + RankingsApp fall back to mock `PICKS`. This means:
- **Demo mode (backend down)**: designers / collaborators see the full mocked slate with Trout/Judge/Acuña.
- **Live mode (backend up)**: real `/picks/today` data flows through `adaptPickSummary`.

The adapter synthesizes fields the API doesn't own (jersey number, handedness, edge). The `edge` is currently a placeholder `expected-HR - base-rate` difference; wiring real book odds is deferred.

## Detail pages don't have a mock fallback

`/player/[id]`, `/matchup/[gamePk]/[batterId]`, `/model` call `notFound()` when the API returns `null`. There's no sensible mock for a specific player/matchup that's not in today's slate. The styled `/not-found` page catches these gracefully.

## Reliability chart is hand-rolled SVG

Stage 5 originally specified `recharts`. It was removed — the aesthetic conflicts with recharts' default visual language (rounded bars, smooth gradients, light theme assumptions), and the data shapes are simple enough that a ~80-line SVG component is cleaner than fighting recharts prop plumbing. `ReliabilityChart.tsx` renders a diagonal ideal-calibration line + polyline + per-bin circles sized by bin count. Any chart we add later (rolling log-loss over time, etc.) should follow the same pattern.

## Next.js version

`create-next-app` pulled Next.js **16.2.4** with React 19.2.4 and Tailwind v4. The PROMPT said 15 but 16 is newer + stable. All features used (App Router, `next/font/google`, `<Link>`, route handlers, ISR with `revalidate`) work identically.

## MLB CDN headshots via plain `<img>`

The duotone treatment stacks CSS filters (`grayscale(1) contrast(1.25)`) + `mix-blend-mode: luminosity` + a radial-gradient overlay. Next.js `<Image>` would own the filter pipeline and fight the composite. Plain `<img>` with `eslint-disable-next-line @next/next/no-img-element` comments is the right trade here.

## Tests

No UI test suite yet. Verification is build + lint + manual walkthrough against the 5-route smoke test. A future `vitest` + `@testing-library/react` pass can cover RankingsApp filters / parlay math; the visual stages (arc, ticket, boot) are best validated by inspection.
