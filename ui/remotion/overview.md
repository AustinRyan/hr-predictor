# ui/remotion/ — Promotional video compositions

**Purpose:** Remotion source for renderable social/promotional assets that share the Homerun brand language without depending on the live Next.js app.

## Entry Points
- `index.ts` registers the Remotion root.
- `Root.tsx` defines renderable compositions and stills.
- `HomerunPromo.tsx` contains the 9:16 promotional reel and poster still.
- `generate-promo-music.mjs` generates the original synth bed at `public/audio/homerun-promo-bed.wav`.

## Public Interface
- `npm run remotion` opens Remotion Studio on port 3001.
- `npm run music:promo` regenerates the promo music bed.
- `npm run render:promo` renders `out/homerun-promo.mp4`.
- `npm run still:promo` renders `out/homerun-promo-poster.png`.

## Gotchas
- Animations must be driven by `useCurrentFrame()` and explicit `fps` timing; avoid CSS transitions/animations because rendered frames need deterministic values.
- Keep generated videos in `ui/out/`, which is already treated as build output.
