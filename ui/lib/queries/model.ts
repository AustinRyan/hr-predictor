/**
 * /model/metrics equivalent.
 *
 * Training metadata + training metrics are hardcoded here because the
 * production model artifacts (`src/models/registry/v.../...json`) live on
 * the user's laptop, not on Vercel. When a new model is promoted, update
 * these constants in the same PR.
 *
 * Rolling-live metrics are computed directly from SQL against the shared
 * Neon database.
 */

import { sql } from "@/lib/db";
import type {
  ModelMetricsResponse,
  ReliabilityBin,
  RollingLiveMetrics,
  TrainingMetadata,
  TrainingMetrics,
} from "@/lib/types";

// From src/models/registry/v20260423_231941/training_metadata.json
const PRODUCTION_METADATA: TrainingMetadata = {
  model_version: "v20260423_231941",
  git_sha: "30306dbf9fdf4dce3da03dc597241b68fcbd7431",
  data_hash: "768ea7ce54a83de878ed4be444061c33558265b1cba96de7e4aeebb5c81ef7a4",
  training_range: ["2021-04-01", "2026-04-21"],
  num_features: 118,
  created_at_utc: "2026-04-23T23:19:41.663360+00:00",
  config: {
    model_type: "xgboost+lightgbm_ensemble",
    n_estimators: 600,
    max_depth: 4,
    learning_rate: 0.05,
    ensemble: "50_50_average",
  },
};

// From src/models/registry/v20260423_231941/metrics.json
const PRODUCTION_METRICS: TrainingMetrics = {
  train_log_loss: 0.17541477537098893,
  val_log_loss: 0.1793938105470933,
  test_log_loss: 0.18010656776599882,
  train_brier: 0.04306182449063401,
  val_brier: 0.043351478697956886,
  test_brier: 0.04343698449209702,
  test_auc: 0.6638959409394987,
  test_ece: 0.006405363004101602,
  test_precision_at_top_k: 0.12116182572614109,
};

function logLoss(actuals: number[], preds: number[]): number {
  const eps = 1e-15;
  let total = 0;
  for (let i = 0; i < actuals.length; i++) {
    const p = Math.min(1 - eps, Math.max(eps, preds[i]!));
    total += -(actuals[i]! * Math.log(p) + (1 - actuals[i]!) * Math.log(1 - p));
  }
  return total / actuals.length;
}

function brierScore(actuals: number[], preds: number[]): number {
  let total = 0;
  for (let i = 0; i < actuals.length; i++) {
    const d = preds[i]! - actuals[i]!;
    total += d * d;
  }
  return total / actuals.length;
}

function reliabilityAndEce(
  actuals: number[],
  preds: number[],
  nBins = 10,
): { bins: ReliabilityBin[]; ece: number } {
  const binSums = new Array(nBins).fill(0);
  const binCounts = new Array(nBins).fill(0);
  const binActualSums = new Array(nBins).fill(0);
  for (let i = 0; i < preds.length; i++) {
    const b = Math.min(nBins - 1, Math.floor(preds[i]! * nBins));
    binSums[b] += preds[i]!;
    binActualSums[b] += actuals[i]!;
    binCounts[b]++;
  }
  const bins: ReliabilityBin[] = [];
  let ece = 0;
  for (let i = 0; i < nBins; i++) {
    const n = binCounts[i];
    const meanPred = n > 0 ? binSums[i] / n : null;
    const actualRate = n > 0 ? binActualSums[i] / n : null;
    if (n > 0 && meanPred !== null && actualRate !== null) {
      ece += (n / preds.length) * Math.abs(meanPred - actualRate);
    }
    bins.push({
      bin_lower: i / nBins,
      bin_upper: (i + 1) / nBins,
      mean_pred: meanPred,
      actual_rate: actualRate,
      count: n,
    });
  }
  return { bins, ece };
}

async function computeRollingLive(
  modelVersion: string,
  windowDays = 30,
): Promise<RollingLiveMetrics> {
  const rows = (await sql`
    SELECT
      p.prob_at_least_one_hr::float AS pred,
      CASE
        WHEN mf.hr_on_pa IS TRUE THEN 1
        WHEN mf.hr_on_pa IS FALSE THEN 0
        ELSE NULL
      END AS actual,
      p.game_date
    FROM predictions p
    JOIN matchup_features mf
      ON mf.game_pk = p.game_pk
     AND mf.batter_id = p.batter_id
     AND mf.pitcher_id = p.pitcher_id
    WHERE p.game_date >= CURRENT_DATE - (${windowDays} || ' days')::interval
      AND p.model_version = ${modelVersion}
      AND mf.is_historical
      AND mf.hr_on_pa IS NOT NULL
  `) as unknown as { pred: number; actual: number; game_date: Date | string }[];

  if (rows.length === 0) {
    return {
      window_days: windowDays,
      n_predictions: 0,
      evaluated_from: null,
      evaluated_to: null,
      log_loss: null,
      brier: null,
      ece: null,
      reliability: [],
    };
  }

  const preds = rows.map((r) => Number(r.pred));
  const actuals = rows.map((r) => Number(r.actual));
  const dates = rows
    .map((r) => (r.game_date instanceof Date ? r.game_date : new Date(r.game_date)))
    .sort((a, b) => a.getTime() - b.getTime());
  const { bins, ece } = reliabilityAndEce(actuals, preds, 10);
  return {
    window_days: windowDays,
    n_predictions: preds.length,
    evaluated_from: dates[0]?.toISOString().slice(0, 10) ?? null,
    evaluated_to: dates[dates.length - 1]?.toISOString().slice(0, 10) ?? null,
    log_loss: logLoss(actuals, preds),
    brier: brierScore(actuals, preds),
    ece,
    reliability: bins,
  };
}

export async function modelMetrics(): Promise<ModelMetricsResponse> {
  const rolling = await computeRollingLive(
    PRODUCTION_METADATA.model_version,
    30,
  );
  return {
    training_metadata: PRODUCTION_METADATA,
    training_metrics: PRODUCTION_METRICS,
    rolling_live: rolling,
  };
}
