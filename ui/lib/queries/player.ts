/**
 * /player/{mlbam_id} equivalent — profile + rolling + today's prediction.
 * Ported from src/api/routers/player.py.
 */

import { sql } from "@/lib/db";
import type { PlayerDetail, PlayerRollingStats, PlayerTodayPrediction, PlayerProfile } from "@/lib/types";

type ProfileRow = PlayerProfile & {
  mlbam_id: number;
};

function n(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const asNum = Number(v);
  return Number.isFinite(asNum) ? asNum : null;
}

export async function playerDetail(mlbamId: number): Promise<PlayerDetail | null> {
  const [profile] = (await sql`
    SELECT mlbam_id, full_name, first_name, last_name,
           bats, throws, primary_position, active
    FROM players
    WHERE mlbam_id = ${mlbamId}
  `) as unknown as ProfileRow[];
  if (!profile) return null;

  const rollingRows = (await sql`
    SELECT
      game_date AS as_of,
      b_barrel_pct_30d, b_hardhit_pct_30d, b_avg_ev_30d, b_p90_ev_30d,
      b_avg_la_30d, b_pulled_fb_pct_30d, b_xwobacon_30d,
      b_hr_per_pa_30d, b_pa_count_30d,
      b_barrel_pct_season, b_hr_per_pa_season, b_pa_count_season
    FROM matchup_features
    WHERE batter_id = ${mlbamId} AND is_historical
    ORDER BY game_date DESC
    LIMIT 1
  `) as unknown as Record<string, unknown>[];

  const rolling: PlayerRollingStats = rollingRows[0]
    ? {
        as_of:
          rollingRows[0].as_of instanceof Date
            ? rollingRows[0].as_of.toISOString().slice(0, 10)
            : (rollingRows[0].as_of as string | null),
        b_barrel_pct_30d: n(rollingRows[0].b_barrel_pct_30d),
        b_hardhit_pct_30d: n(rollingRows[0].b_hardhit_pct_30d),
        b_avg_ev_30d: n(rollingRows[0].b_avg_ev_30d),
        b_p90_ev_30d: n(rollingRows[0].b_p90_ev_30d),
        b_avg_la_30d: n(rollingRows[0].b_avg_la_30d),
        b_pulled_fb_pct_30d: n(rollingRows[0].b_pulled_fb_pct_30d),
        b_xwobacon_30d: n(rollingRows[0].b_xwobacon_30d),
        b_hr_per_pa_30d: n(rollingRows[0].b_hr_per_pa_30d),
        b_pa_count_30d: n(rollingRows[0].b_pa_count_30d),
        b_barrel_pct_season: n(rollingRows[0].b_barrel_pct_season),
        b_hr_per_pa_season: n(rollingRows[0].b_hr_per_pa_season),
        b_pa_count_season: n(rollingRows[0].b_pa_count_season),
      }
    : {
        as_of: null,
        b_barrel_pct_30d: null,
        b_hardhit_pct_30d: null,
        b_avg_ev_30d: null,
        b_p90_ev_30d: null,
        b_avg_la_30d: null,
        b_pulled_fb_pct_30d: null,
        b_xwobacon_30d: null,
        b_hr_per_pa_30d: null,
        b_pa_count_30d: null,
        b_barrel_pct_season: null,
        b_hr_per_pa_season: null,
        b_pa_count_season: null,
      };

  // Use most-recent prediction date instead of UTC today: inference runs
  // locally on the user's laptop so "today" on the deployed site may be
  // a day ahead of the last inference run.
  const predRows = (await sql`
    SELECT game_pk, pitcher_id, prob_at_least_one_hr,
           expected_hrs, projected_pas, model_version
    FROM predictions
    WHERE batter_id = ${mlbamId}
      AND game_date = (SELECT MAX(game_date) FROM predictions WHERE batter_id = ${mlbamId})
    ORDER BY prob_at_least_one_hr DESC
    LIMIT 1
  `) as unknown as Record<string, unknown>[];

  const today_prediction: PlayerTodayPrediction | null = predRows[0]
    ? {
        game_pk: Number(predRows[0].game_pk),
        pitcher_id: Number(predRows[0].pitcher_id),
        prob_at_least_one_hr: Number(predRows[0].prob_at_least_one_hr),
        expected_hrs: n(predRows[0].expected_hrs),
        projected_pas: n(predRows[0].projected_pas),
        model_version: String(predRows[0].model_version),
      }
    : null;

  return {
    profile: {
      mlbam_id: profile.mlbam_id,
      full_name: profile.full_name,
      first_name: profile.first_name,
      last_name: profile.last_name,
      bats: profile.bats,
      throws: profile.throws,
      primary_position: profile.primary_position,
      active: profile.active,
    },
    rolling,
    today_prediction,
  };
}
