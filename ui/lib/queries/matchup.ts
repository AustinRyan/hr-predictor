/**
 * /matchup/{game_pk}/{batter_id} equivalent — full breakdown of inputs
 * + SHAP that drove one specific prediction. Ported from
 * src/api/routers/matchup.py.
 */

import { sql } from "@/lib/db";
import type {
  BatterProfile,
  FeatureContribution,
  GameContext,
  MatchupDetail,
  ParkContext,
  PitcherProfile,
  PredictionBreakdown,
  WeatherContext,
} from "@/lib/types";

function n(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const asNum = Number(v);
  return Number.isFinite(asNum) ? asNum : null;
}

function topContribs(raw: Record<string, number> | null): FeatureContribution[] {
  if (!raw) return [];
  return Object.entries(raw)
    .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
    .slice(0, 10)
    .map(([name, contribution]) => ({ name, contribution: Number(contribution) }));
}

export async function matchupDetail(
  gamePk: number,
  batterId: number,
): Promise<MatchupDetail | null> {
  const mfRows = (await sql`
    SELECT
      mf.*,
      ds.game_start_utc,
      pk.name AS park_name,
      pk.elevation_ft AS park_elev_ft,
      pk.roof_type AS park_roof_type,
      COALESCE(bp.full_name, odds_name.player_name) AS batter_full_name,
      bp.bats AS batter_bats,
      pp.full_name AS pitcher_full_name,
      pp.throws AS pitcher_throws,
      tm_home.abbr AS home_abbr,
      tm_away.abbr AS away_abbr
    FROM matchup_features mf
    LEFT JOIN daily_schedule ds ON ds.game_pk = mf.game_pk
    LEFT JOIN parks pk ON pk.park_id = mf.park_id
    LEFT JOIN players bp ON bp.mlbam_id = mf.batter_id
    LEFT JOIN players pp ON pp.mlbam_id = mf.pitcher_id
    LEFT JOIN LATERAL (
      SELECT os.player_name
      FROM odds_snapshots os
      WHERE os.game_pk = mf.game_pk
        AND os.batter_id = mf.batter_id
        AND os.market_key = 'batter_home_runs'
        AND os.outcome_name IN ('Over', 'Yes')
        AND (os.point IS NULL OR ABS(os.point - 0.5) < 0.000001)
        AND COALESCE(os.raw_outcome->>'name', '') !~*
          '^\\s*[2-9][0-9]*\\+\\s+home runs?\\s*$'
      ORDER BY os.fetched_at DESC, os.market_last_update DESC NULLS LAST, os.id DESC
      LIMIT 1
    ) odds_name ON TRUE
    LEFT JOIN teams tm_home ON tm_home.team_id = ds.home_team_id
    LEFT JOIN teams tm_away ON tm_away.team_id = ds.away_team_id
    WHERE mf.game_pk = ${gamePk} AND mf.batter_id = ${batterId}
    ORDER BY mf.game_date DESC
    LIMIT 1
  `) as unknown as Record<string, unknown>[];
  if (!mfRows[0]) return null;
  const r = mfRows[0];

  const predRows = (await sql`
    SELECT prob_at_least_one_hr, prob_at_least_two_hr, expected_hrs,
           matchup_components, feature_contributions, model_version, generated_at
    FROM predictions
    WHERE game_pk = ${gamePk} AND batter_id = ${batterId}
    ORDER BY generated_at DESC
    LIMIT 1
  `) as unknown as Record<string, unknown>[];

  let prediction: PredictionBreakdown | null = null;
  if (predRows[0]) {
    const p = predRows[0];
    const mc = (p.matchup_components ?? {}) as Record<string, number | string | null>;
    prediction = {
      prob_at_least_one_hr: n(p.prob_at_least_one_hr),
      prob_at_least_two_hr: n(p.prob_at_least_two_hr),
      expected_hrs: n(p.expected_hrs),
      starter_raw_prob: n(mc.starter_raw_prob),
      starter_calibrated_prob: n(mc.starter_calibrated_prob),
      probability_semantics: (mc.probability_semantics as string | null) ?? null,
      full_game_raw_prob: n(mc.full_game_raw_prob),
      full_game_calibrated_prob: n(mc.full_game_calibrated_prob),
      starter_signal_source: (mc.starter_signal_source as string | null) ?? null,
      bullpen_raw_prob: n(mc.bullpen_raw_prob),
      bullpen_calibrated_prob: n(mc.bullpen_calibrated_prob),
      top_contributing_features: topContribs(
        p.feature_contributions as Record<string, number> | null,
      ),
      model_version: (p.model_version as string | null) ?? null,
      generated_at: p.generated_at
        ? new Date(p.generated_at as string).toISOString()
        : null,
    };
  }

  const game: GameContext = {
    game_pk: Number(r.game_pk),
    game_date:
      r.game_date instanceof Date
        ? r.game_date.toISOString().slice(0, 10)
        : String(r.game_date),
    game_start_utc: r.game_start_utc
      ? new Date(r.game_start_utc as string).toISOString()
      : null,
    home_team_abbr: (r.home_abbr as string | null) ?? null,
    away_team_abbr: (r.away_abbr as string | null) ?? null,
    ctx_batting_order: n(r.ctx_batting_order),
    ctx_projected_pa: n(r.ctx_projected_pa),
    ctx_is_home: (r.ctx_is_home as boolean | null) ?? null,
    ctx_day_night: (r.ctx_day_night as string | null) ?? null,
    ctx_same_hand: (r.ctx_same_hand as boolean | null) ?? null,
  };
  const batter: BatterProfile = {
    mlbam_id: Number(r.batter_id),
    full_name: (r.batter_full_name as string | null) ?? null,
    bats: (r.batter_bats as string | null) ?? null,
    b_barrel_pct_season: n(r.b_barrel_pct_season),
    b_p90_ev_season: n(r.b_p90_ev_season),
    b_avg_ev_season: n(r.b_avg_ev_season),
    b_pulled_fb_pct_season: n(r.b_pulled_fb_pct_season),
    b_hr_per_pa_season: n(r.b_hr_per_pa_season),
    b_vs_lhp_hr_per_pa_reg: n(r.b_vs_lhp_hr_per_pa_reg),
    b_vs_rhp_hr_per_pa_reg: n(r.b_vs_rhp_hr_per_pa_reg),
    b_pa_count_season: n(r.b_pa_count_season),
  };
  const pitcher: PitcherProfile = {
    mlbam_id: Number(r.pitcher_id),
    full_name: (r.pitcher_full_name as string | null) ?? null,
    throws: (r.pitcher_throws as string | null) ?? null,
    p_hr_per_9_season: n(r.p_hr_per_9_season),
    p_barrel_pct_allowed_season: n(r.p_barrel_pct_allowed_season),
    p_vs_lhb_hr_rate: n(r.p_vs_lhb_hr_rate),
    p_vs_rhb_hr_rate: n(r.p_vs_rhb_hr_rate),
    p_primary_pitch: (r.p_primary_pitch as string | null) ?? null,
    p_ff_velo_avg: n(r.p_ff_velo_avg),
    p_tto_penalty: n(r.p_tto_penalty),
  };
  const park: ParkContext = {
    park_id: n(r.park_id),
    park_name: (r.park_name as string | null) ?? null,
    elevation_ft: n(r.park_elev_ft),
    roof_type: (r.park_roof_type as string | null) ?? null,
    park_hr_factor_hand: n(r.park_hr_factor_hand),
    park_hr_factor_hand_3yr: n(r.park_hr_factor_hand_3yr),
  };
  const weather: WeatherContext = {
    temperature_f: n(r.wx_temperature_f),
    humidity_pct: n(r.wx_humidity_pct),
    wind_speed_mph: n(r.wx_wind_speed_mph),
    wind_direction_deg: null,
    air_density_relative: n(r.wx_air_density_relative),
    wind_carry_lf: n(r.wx_wind_carry_lf),
    wind_carry_cf: n(r.wx_wind_carry_cf),
    wind_carry_rf: n(r.wx_wind_carry_rf),
    is_roof_closed: (r.wx_is_roof_closed as boolean | null) ?? null,
  };

  return { game, batter, pitcher, park, weather, prediction };
}
