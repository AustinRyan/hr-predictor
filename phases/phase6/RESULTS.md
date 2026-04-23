# Phase 6 — Results

Full FastAPI backend shipped with `/health`, `/picks/today`, `/player/{id}`,
`/matchup/{game_pk}/{batter_id}`, `/model/metrics`. Redis cache for read
endpoints. SHAP-backed feature contributions at inference time.

## Inference pipeline

- Command: `uv run python -m src.models.inference`
- Today (2026-04-23): wrote **135 predictions** across **9 games**.
- Top P(≥1 HR): **0.1025** — 5-way tie at the isotonic calibrator ceiling
  (Ramón Laureano @ Coors, Gary Sánchez vs Skubal @ Comerica, Ketel Marte
  @ Chase, Bryce Harper @ Wrigley, Shohei Ohtani vs Webb @ Oracle Park).
- Mean P(≥1 HR): **0.0506** (close to the 4.65% base rate, as expected).
- Wall time: ~30 ms end-to-end (feature pull + model predict + calibration
  + SHAP via `Booster.pred_contribs` + upsert for 135 rows).
- Idempotent: re-run produces identical row count, upserts cleanly, only
  `generated_at` advances.

## Endpoint latencies (warm DB + warm Redis)

All measurements against `127.0.0.1:8765`, single-process `uvicorn`,
local Docker Postgres + Redis.

| endpoint                                  | latency   |
|-------------------------------------------|-----------|
| `/health`                                 | 23.5 ms   |
| `/picks/today?limit=20` (cold)            | 30.6 ms   |
| `/picks/today?limit=20` (warm, cached)    | 20.3 ms   |
| `/picks/today?limit=7&sort=prob` (cold)   | 12.7 ms   |
| `/picks/today?limit=7&sort=prob` (warm)   | 0.9–1.1 ms |
| `/matchup/823233/660271`                  | 30.7 ms   |
| `/model/metrics`                          | 29.9 ms   |

Acceptance bars (`/picks/today` < 500 ms cold / < 50 ms warm,
`/matchup` < 1 s) hit by an order of magnitude.

## Cache behavior

Flushed `picks:*` keys, then hit `/picks/today?limit=7&sort=prob` three
times while sampling `redis INFO stats`:

- Hits delta: +2
- Misses delta: +1
- Warm-call wall time: 0.9–1.1 ms vs cold 12.7 ms.

Cache keys observed in Redis: `picks:today:<hash>`, `player:detail:<hash>`.
No `matchup:*` entries (matchup is intentionally uncached — PROMPT §4).

## Model metrics (snapshot — initial ship, v20260423_173917)

- Version: **v20260423_173917** (no longer PRODUCTION — superseded)
- Training range: 2021-04-01 → 2026-04-21 (120 features)
- Test log_loss: **0.17840**
- Test Brier: **0.04324** (≈ the 0.0443 base-rate floor at 4.65% HR rate)
- Test ECE: **0.00473**
- Test AUC: **0.67930** *(inflated by `ctx_pitcher_days_rest` shortcut)*
- Test precision@top-20: **0.13237**
- Rolling live (last 30 days): **0 predictions evaluated** — today is
  day-1 of live predictions; no outcomes-known horizon yet. The
  `/model/metrics` endpoint returns the block with `n_predictions=0`
  and null metric values (the expected shape for an empty window).

## Post-ship promotion: ensemble v20260423_231941 (PRODUCTION)

After a failed smell-test (Sánchez vs Skubal in top-5 driven by
`ctx_pitcher_days_rest` +0.38 SHAP), dropped both `ctx_*_days_rest`
columns from FEATURE_COLUMNS (120 → 118) and ran the Option 3 sweep.
See `phases/phase6/NOTES.md` for the full narrative and sweep table.

- Version: **v20260423_231941** (PRODUCTION)
- Ensemble: **50/50 XGBoost (tuned_conservative) + LightGBM**
- Training range: 2021-04-01 → 2026-04-21 (118 features)
- Test log_loss: **0.18011** (+0.0017 vs old)
- Test Brier: **0.04344** (essentially unchanged)
- Test ECE: **0.00641** (below the 0.03 bar, calibration still tight)
- Test AUC: **0.66389** (−0.015 — the leak-shortcut tax)
- Test precision@top-20: **0.12116**

Trade-off: legitimate SHAP interpretability over leak-assisted AUC.

## Refreshed picks under ensemble (2026-04-23)

Top-10 `P(≥1 HR)` under the ensemble, with top-3 SHAP drivers per pick:

| rank | batter             | pitcher         | p     | top SHAP drivers                               |
|-----:|--------------------|-----------------|------:|------------------------------------------------|
| 1    | james wood         | (NL game)       | 0.1158 | b_p90_ev_30d, p_cu_usage, b_barrel_pct_season |
| 2    | ketel marte        | davis martin    | 0.1158 | p_ch_usage, b_p90_ev_season, p_cu_usage       |
| 3    | (WSOX game)        | michael soroka  | 0.1132 | b_p90_ev_30d, park_hr_factor_hand, b_xiso     |
| 4    | gary sánchez       | tarik skubal    | 0.0927 | p_ff_velo_avg, p_ch_usage, ctx_same_hand      |
| 5    | colson montgomery  | michael soroka  | 0.0927 | park_hr_factor_hand, p_ch_usage, ctx_same_hand|
| 6    | cj abrams          | (NL game)       | 0.0901 | p_ch_usage, p_cu_usage, p_k_pct               |
| 7    | shohei ohtani      | logan webb      | 0.0901 | park_hr_factor_hand, b_xiso_season, ctx_same_hand |
| 8    | jackson merrill    | ryan feltner    | 0.0901 | p_ch_usage, bp_hr_per_9_season, b_xiso_season |
| 9    | giancarlo stanton  | payton tolle    | 0.0901 | p_ff_velo_avg, b_p90_ev_30d, p_hardhit_pct    |
| 10   | corbin carroll     | davis martin    | 0.0901 | park_hr_factor_hand, p_ch_usage, b_xiso_season|

Max P(≥1 HR) 0.1158 (James Wood, Ketel Marte). Mean 0.0447 (close
to 4.65% base rate, as expected). **No `ctx_*_days_rest` in the top
SHAP features anywhere in the day's picks** — the leaky shortcut is
gone. Sánchez-vs-Skubal is still in the board but at rank 4 and
driven by `p_ff_velo_avg` (Skubal's velo) + `ctx_same_hand`, not a
rest-day ID fingerprint.

## Sample `/picks/today?limit=5` response

```json
[
  {
    "batter_id": 657656,
    "batter_name": "ramón laureano",
    "game_pk": 824368,
    "park_name": "Coors Field",
    "pitcher_name": "ryan feltner",
    "prob_at_least_one_hr": 0.1025,
    "expected_hrs": 0.1025,
    "top_contributing_features": [
      {"name": "ctx_pitcher_days_rest", "contribution": 0.362},
      {"name": "b_xiso_season",         "contribution": 0.135},
      {"name": "ctx_batting_order",     "contribution": 0.095}
    ],
    "model_version": "v20260423_173917"
  }
  ...
]
```

See `reports/phase6_inference.log` for the full inference run log.
