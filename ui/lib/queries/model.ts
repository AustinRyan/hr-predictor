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

// From src/models/registry/v20260510_163447/training_metadata.json
const PRODUCTION_METADATA: TrainingMetadata = {
  model_version: "v20260510_163447",
  git_sha: "35944b4c1f12f26797ceef9ab08b72bfd493f4bb",
  data_hash: null,
  training_range: ["2021-04-01", "2026-04-21"],
  num_features: 127,
  created_at_utc: null,
  config: {
    model_type: "xgboost",
    n_estimators: 500,
    max_depth: 5,
    learning_rate: 0.05,
    target: "full_game_hr",
    uses_team_bullpen_features: true,
  },
};

// From src/models/registry/v20260510_163447/metrics.json
const PRODUCTION_METRICS: TrainingMetrics = {
  train_log_loss: 0.33341564939928503,
  val_log_loss: 0.34071741197359,
  test_log_loss: 0.34261646922575895,
  train_brier: 0.09710433912643678,
  val_brier: 0.09815293394212818,
  test_brier: 0.09852788145935082,
  test_auc: 0.6474805879509337,
  test_ece: 0.004617698121894374,
  test_precision_at_top_k: 0.22367256637168142,
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
    WITH settled_games AS (
      SELECT DISTINCT game_pk
      FROM statcast_pitches
      WHERE game_date >= CURRENT_DATE - (${windowDays - 1} || ' days')::interval
    )
    SELECT
      p.prob_at_least_one_hr::float AS pred,
      CASE WHEN EXISTS (
        SELECT 1
        FROM statcast_pitches sp_hr
        WHERE sp_hr.game_pk = p.game_pk
          AND sp_hr.batter = p.batter_id
          AND sp_hr.events = 'home_run'
      ) THEN 1 ELSE 0 END AS actual,
      p.game_date
    FROM predictions p
    JOIN settled_games sg ON sg.game_pk = p.game_pk
    WHERE p.game_date >= CURRENT_DATE - (${windowDays - 1} || ' days')::interval
      AND p.model_version = ${modelVersion}
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
