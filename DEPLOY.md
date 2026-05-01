# Deploy to Vercel

The frontend queries Neon Postgres directly, so there's no backend to host.
Your laptop runs inference locally and writes to the same Neon DB the
deployed site reads.

## Current state

- **Neon**: schema + 2026 season data already migrated (see
  `scripts/refresh-picks.sh` to write more).
- **Code**: `ui/lib/api.ts` no longer hits FastAPI. `lib/queries/*`
  talk to Postgres via the `postgres` npm package.
- **Env-gated refresh button**: `NEXT_PUBLIC_ALLOW_REFRESH=true` shows
  it locally; unset on Vercel so production users can't click a button
  whose backend isn't hosted.

## One-time Vercel setup

1. Push this repo to GitHub (done — see `git remote -v`).
2. Go to <https://vercel.com/new>.
3. Select the `hr-predictor` repo.
4. **Root Directory**: change to `ui`. Vercel autodetects Next.js and uses
   default build settings.
5. Under **Environment Variables**, add:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | Paste the pooled Neon connection string from your Neon dashboard. Do not commit the value. |

   Do NOT set `NEXT_PUBLIC_ALLOW_REFRESH` — keep the button hidden in prod.

6. Click **Deploy**. First build takes ~2 min.
7. Your site is live at `https://hr-predictor-<random>.vercel.app`.

Every future `git push origin main` auto-deploys.

## Daily usage (writing fresh picks to Neon)

```sh
# From the repo root on your laptop:
./scripts/refresh-picks.sh
```

This runs ingest → feature build → inference end-to-end against Neon
(because your local `.env` DATABASE_URL points there now). Takes ~2-5
minutes for a typical slate. The deployed Vercel site picks up the new
picks on the next page load.

You can also keep clicking the "REFRESH PICKS" button on
`http://localhost:3000` — same effect, routed through the local FastAPI.

## What's still local-only

- FastAPI (`src/api/`) — runs at `localhost:8765`, not deployed
- Docker Postgres — no longer required (Neon is the source of truth)
- Docker Redis — only used by FastAPI caching; Vercel bypasses it
- Model artifacts (`src/models/registry/`) — needed for inference, stay on
  your laptop

## If you promote a new model

Update the hardcoded training metadata constants in
`ui/lib/queries/model.ts` (the `PRODUCTION_METADATA` and
`PRODUCTION_METRICS` blocks) and push. The `/model` page displays those
values; rolling-live metrics are computed from Neon on each request so
they update automatically.
