---
name: refresh-picks
description: Use when the user asks to "run the model", "update predictions", "refresh picks", "get today's picks", or otherwise wants fresh HR predictions to land on the deployed Vercel site. Runs the full daily pipeline (schedule + lineups + weather + statcast + matchup_features + inference) against the Neon database. Production reads from the same Neon DB, so a successful run is visible on prod within seconds.
---

# Refresh Picks for the Deployed Site

## When to use this skill

The user says any of:
- "run the model"
- "update the database"
- "get new / fresh / today's picks"
- "refresh the predictions"
- "the site shows yesterday's data, fix it"
- "it's a new day, update"

## What it does

Executes `./scripts/refresh-picks.sh` from the repo root. That script:

1. Ingests today's MLB schedule + posted lineups (from MLB StatsAPI)
2. Fetches today's weather forecasts (Open-Meteo)
3. Backfills the last 7 days of Statcast pitches (covers any games not yet ingested)
4. **Fills proxy lineups** for teams whose lineup isn't posted yet (copies their most recent prior lineup with `is_confirmed=False`). Idempotent — only fills gaps.
5. Builds `matchup_features` rows for the target date, including opponent-team bullpen context (`opp_bp_*`) when the database is on migration `0008+`
6. Runs inference with the production model version pointed to by `src/models/registry/PRODUCTION`
7. Upserts predictions into the `predictions` table
8. Fetches PropLine sportsbook odds when `PROP_LINE_API_KEY` is set; odds failures are reported without aborting predictions

All writes go to **Neon** because the repo's `.env` already points there. The deployed Vercel frontend reads the same Neon DB, so a hard-refresh on the live URL shows the new picks immediately.

Typical wall time: **30-90 seconds** (most of it is the Statcast incremental + weather API calls).

## Procedure

### 1. Run the pipeline

```sh
cd /Users/austinryan/Desktop/sideproject/hr-predictor
./scripts/refresh-picks.sh
```

Use the Bash tool. Expect output ending in:

```
[3/4] building matchup_features + running inference
  matchup_features rows: <N>
  predictions written: <N>

[4/4] fetching sportsbook odds
  odds_rows=<N> ...

✓ refresh complete for YYYY-MM-DD
```

### 2. Verify the data landed

Run a quick Python check to show the top 10 picks for today (proves the pipeline succeeded AND the values look reasonable):

```sh
uv run python -u -c "
from src.core.db import get_session
from sqlalchemy import text
with get_session() as s:
    rows = s.execute(text('''
        SELECT p.full_name, pr.prob_at_least_one_hr,
               pr.matchup_components->>'probability_semantics' AS semantics,
               pi.full_name AS pitcher, pk.name AS park
        FROM predictions pr
        JOIN players p ON p.mlbam_id = pr.batter_id
        LEFT JOIN players pi ON pi.mlbam_id = pr.pitcher_id
        LEFT JOIN daily_schedule ds ON ds.game_pk = pr.game_pk
        LEFT JOIN parks pk ON pk.park_id = ds.venue_id
        WHERE pr.game_date = (SELECT MAX(game_date) FROM predictions)
        ORDER BY pr.prob_at_least_one_hr DESC LIMIT 10
    ''')).all()
    for r in rows:
        pct = float(r.prob_at_least_one_hr) * 100
        semantics = r.semantics or 'starter_matchup_hr'
        print(f'  {r.full_name:<22s} vs {r.pitcher or \"—\":<22s} @ {r.park or \"—\":<22s} {pct:.1f}% {semantics}')
"
```

Use the Bash tool. The output should be a clean list of real MLB players + pitcher matchups + parks.

### 3. Report to the user

Tell them:
- How many predictions were written
- The slate size (number of unique games)
- The top 1-3 picks with names + probabilities + parks
- Whether probabilities are `full_game_hr` or `starter_matchup_hr`
- That they can hard-refresh the live site (`localhost:3000` for local dev, or their Vercel URL) to see fresh picks

Example:
> Pipeline ran clean — 243 predictions across 15 games. Top picks: Murakami 16.7% vs Jake Irvin @ Rate Field, then Caminero/Muncy/Ohtani/Stanton tied at 15.4%. Vercel reads from the same Neon DB so a hard-refresh shows them immediately.

## Common situations

### "Lineups aren't posted yet" (early in the day)

The script handles this automatically via the proxy-lineup fallback. The output line `proxy lineup rows inserted: N` (where N > 0) confirms the fallback fired. Predictions are still generated; they just use yesterday's starters as a stand-in for any team whose card isn't out yet.

When MLB later publishes today's actual lineups (~3-5 hours before first pitch), running the script again **replaces** the proxy rows with `is_confirmed=True` real lineups, rebuilds features for any swapped batters, and updates predictions. Idempotent — safe to re-run as many times as the user wants.

### "MLB hasn't posted any games today" (very rare — off-day, All-Star break, lockout)

The script reports `games=0` and writes 0 predictions. Don't hide this — tell the user "no MLB games today" and stop.

### "Statcast backfill failed"

Look at the failure list at the end of the run. Most commonly it's a transient pybaseball / Baseball Savant timeout — re-running usually fixes it. If a specific date keeps failing, that's a real issue to dig into.

### "Odds failed but predictions completed"

This is safe to report as an odds-provider issue. The predictions and matchup features are current; sportsbook edge/EV will be missing or stale until the odds step succeeds on a later rerun.

### "The user asks whether bullpen is included"

The refresh script builds opponent-team bullpen features every run. They affect the headline probability only when the promoted artifact was trained with `target="full_game_hr"` and the `opp_bp_*` fields in its feature schema. Older starter-matchup artifacts still expose bullpen fields for display/debugging but do not use them in probability generation.

## What NOT to do

- **Don't** call FastAPI's `POST /admin/refresh-picks` endpoint as a substitute. The CLI script is the source of truth; the API endpoint is just a UI convenience for the local dev experience.
- **Don't** push to git as part of this skill — running the model does NOT change code, only data in Neon. Pushing is for actual code changes.
- **Don't** restart the dev server or Vercel deployment. The frontend re-reads Neon on every page load, so fresh picks appear automatically.
- **Don't** manually edit `predictions` rows in Postgres. Always go through the script so all 243 rows are coherent (same model_version, same feature snapshot).

## Related files

- `scripts/refresh-picks.sh` — the orchestrator
- `src/ingestion/daily_runner.py` — schedule + lineup + weather + statcast ingest
- `src/features/builder.py::build_features_for_today` — feature build
- `src/models/inference.py::generate_predictions_for_date` — model inference
- `src/api/routers/admin.py` — same logic exposed as an HTTP endpoint for the local UI's REFRESH PICKS button
- `DEPLOY.md` — Vercel deploy + daily-usage doc
