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

## Model metrics (snapshot)

- Version: **v20260423_173917** (PRODUCTION)
- Training range: 2021-04-01 → 2026-04-21 (120 features)
- Test log_loss: **0.17840**
- Test Brier: **0.04324** (≈ the 0.0443 base-rate floor at 4.65% HR rate)
- Test ECE: **0.00473**
- Test AUC: **0.67930**
- Test precision@top-20: **0.13237**
- Rolling live (last 30 days): **0 predictions evaluated** — today is
  day-1 of live predictions; no outcomes-known horizon yet. The
  `/model/metrics` endpoint returns the block with `n_predictions=0`
  and null metric values (the expected shape for an empty window).

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
