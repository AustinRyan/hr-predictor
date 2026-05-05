/**
 * /picks/today equivalent — returns ranked HR picks for today (or the
 * most recent date with predictions, since inference runs locally on
 * the user's laptop and may lag by a day).
 *
 * SQL is a near-verbatim port of src/api/routers/picks.py. Any change
 * to PickSummary contract or join shape should be mirrored there.
 */

import { sql } from "@/lib/db";
import type { FeatureContribution, PickSummary } from "@/lib/types";

type Row = {
  game_pk: number;
  game_date: Date;
  batter_id: number;
  pitcher_id: number;
  prob_at_least_one_hr: string; // numeric comes back as string
  expected_hrs: string | null;
  model_rank_score: string | null;
  feature_contributions: Record<string, number> | null;
  model_version: string;
  odds_bookmaker_key: string | null;
  odds_bookmaker: string | null;
  odds_price_american: number | null;
  odds_point: string | null;
  market_implied_probability: string | null;
  market_no_vig_probability: string | null;
  fair_odds_american: number | null;
  model_edge: string | null;
  expected_value_per_unit: string | null;
  odds_fetched_at: Date | null;
  game_start_utc: Date | null;
  batter_name: string | null;
  batter_bats: string | null;
  batter_position: string | null;
  pitcher_name: string | null;
  pitcher_throws: string | null;
  park_name: string | null;
  b_barrel_pct_season: string | null;
  b_p90_ev_season: string | null;
  park_hr_factor_hand: string | null;
  p_hr_per_9_season: string | null;
  p_barrel_pct_allowed_season: string | null;
  ctx_batting_order: number | null;
  ctx_projected_pa: string | null;
  wx_wind_carry_cf: string | null;
  wx_temperature_f: string | null;
  wx_air_density_relative: string | null;
  team_abbr: string | null;
  home_abbr: string | null;
  away_abbr: string | null;
};

function topContribs(raw: Record<string, number> | null): FeatureContribution[] {
  if (!raw) return [];
  return Object.entries(raw)
    .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
    .slice(0, 5)
    .map(([name, contribution]) => ({ name, contribution: Number(contribution) }));
}

function toPick(row: Row): PickSummary {
  const n = (s: string | null): number | null => (s === null ? null : Number(s));
  return {
    batter_id: Number(row.batter_id),
    batter_name: row.batter_name,
    batter_bats: row.batter_bats,
    batter_position: row.batter_position,
    team_abbr: row.team_abbr,
    game_pk: Number(row.game_pk),
    game_date:
      row.game_date instanceof Date
        ? row.game_date.toISOString().slice(0, 10)
        : String(row.game_date),
    game_start_utc: row.game_start_utc
      ? new Date(row.game_start_utc).toISOString()
      : null,
    park_name: row.park_name,
    home_team_abbr: row.home_abbr,
    away_team_abbr: row.away_abbr,
    pitcher_id: Number(row.pitcher_id),
    pitcher_name: row.pitcher_name,
    pitcher_throws: row.pitcher_throws,
    prob_at_least_one_hr: Number(row.prob_at_least_one_hr),
    expected_hrs: n(row.expected_hrs),
    model_rank_score: n(row.model_rank_score),
    odds_bookmaker: row.odds_bookmaker,
    odds_bookmaker_key: row.odds_bookmaker_key,
    odds_price_american:
      row.odds_price_american === null ? null : Number(row.odds_price_american),
    odds_point: n(row.odds_point),
    market_implied_probability: n(row.market_implied_probability),
    market_no_vig_probability: n(row.market_no_vig_probability),
    fair_odds_american:
      row.fair_odds_american === null ? null : Number(row.fair_odds_american),
    model_edge: n(row.model_edge),
    expected_value_per_unit: n(row.expected_value_per_unit),
    odds_fetched_at: row.odds_fetched_at ? new Date(row.odds_fetched_at).toISOString() : null,
    barrel_pct_season: n(row.b_barrel_pct_season),
    p90_ev_season: n(row.b_p90_ev_season),
    park_hr_factor_hand: n(row.park_hr_factor_hand),
    pitcher_hr_per_9_season: n(row.p_hr_per_9_season),
    pitcher_barrel_pct_allowed_season: n(row.p_barrel_pct_allowed_season),
    batting_order: row.ctx_batting_order === null ? null : Number(row.ctx_batting_order),
    projected_pas: n(row.ctx_projected_pa),
    wind_carry_cf: n(row.wx_wind_carry_cf),
    temperature_f: n(row.wx_temperature_f),
    air_density_relative: n(row.wx_air_density_relative),
    top_contributing_features: topContribs(row.feature_contributions),
    model_version: row.model_version,
  };
}

export type PicksQuery = {
  limit?: number;
  minProb?: number;
  team?: string;
  sort?: "prob" | "expected_hrs";
};

function currentMlbDateString(now = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (type: string): string => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

async function activeModelVersion(): Promise<string | null> {
  const [row] = (await sql`
    WITH latest_date AS (
      SELECT MAX(game_date) AS d FROM predictions
    )
    SELECT p.model_version
    FROM predictions p
    JOIN latest_date ld ON p.game_date = ld.d
    GROUP BY p.model_version
    ORDER BY COUNT(*) DESC, MAX(p.generated_at) DESC NULLS LAST
    LIMIT 1
  `) as unknown as { model_version: string | null }[];
  return row?.model_version ?? null;
}

async function queryForDate(
  targetDate: string,
  q: PicksQuery,
  modelVersion: string,
): Promise<PickSummary[]> {
  const limit = q.limit ?? 20;
  const minProb = q.minProb ?? 0;
  const team = q.team ?? null;
  const sortByEhr = q.sort === "expected_hrs";
  const rows = (await sql`
    WITH latest_book_odds AS (
      SELECT
        os.*,
        ROW_NUMBER() OVER (
          PARTITION BY
            os.game_pk,
            os.batter_id,
            os.market_key,
            os.outcome_name,
            os.bookmaker_key,
            os.point
          ORDER BY
            os.fetched_at DESC,
            os.market_last_update DESC NULLS LAST,
            os.id DESC
        ) AS rn
      FROM odds_snapshots os
      WHERE os.game_date = ${targetDate}
        AND os.market_key = 'batter_home_runs'
        AND os.outcome_name IN ('Over', 'Yes')
        AND os.batter_id IS NOT NULL
        AND (os.point IS NULL OR ABS(os.point - 0.5) < 0.000001)
        AND COALESCE(os.raw_outcome->>'name', '') !~*
          '^\\s*[2-9][0-9]*\\+\\s+home runs?\\s*$'
    ),
    best_odds AS (
      SELECT DISTINCT ON (game_pk, batter_id)
        game_pk,
        batter_id,
        bookmaker_key,
        bookmaker_title,
        price_american,
        point,
        implied_probability,
        no_vig_probability,
        fetched_at
      FROM latest_book_odds
      WHERE rn = 1
      ORDER BY game_pk, batter_id, price_american DESC, fetched_at DESC
    )
    SELECT
      p.game_pk,
      p.game_date,
      p.batter_id,
      p.pitcher_id,
      p.prob_at_least_one_hr,
      p.expected_hrs,
      COALESCE(
        NULLIF(p.matchup_components->>'starter_raw_prob', '')::double precision,
        p.prob_at_least_one_hr
      ) AS model_rank_score,
      p.feature_contributions,
      p.model_version,
      bo.bookmaker_key AS odds_bookmaker_key,
      bo.bookmaker_title AS odds_bookmaker,
      bo.price_american AS odds_price_american,
      bo.point AS odds_point,
      bo.implied_probability AS market_implied_probability,
      bo.no_vig_probability AS market_no_vig_probability,
      (
        CASE
          WHEN p.prob_at_least_one_hr <= 0 OR p.prob_at_least_one_hr >= 1 THEN NULL
          WHEN p.prob_at_least_one_hr >= 0.5 THEN
            ROUND(-100.0 * p.prob_at_least_one_hr / (1.0 - p.prob_at_least_one_hr))
          ELSE
            ROUND(100.0 * (1.0 - p.prob_at_least_one_hr) / p.prob_at_least_one_hr)
        END
      )::int AS fair_odds_american,
      CASE
        WHEN bo.implied_probability IS NULL THEN NULL
        ELSE p.prob_at_least_one_hr - bo.implied_probability
      END AS model_edge,
      CASE
        WHEN bo.price_american IS NULL THEN NULL
        WHEN bo.price_american > 0 THEN
          p.prob_at_least_one_hr * (bo.price_american::float / 100.0)
          - (1.0 - p.prob_at_least_one_hr)
        ELSE
          p.prob_at_least_one_hr * (100.0 / ABS(bo.price_american)::float)
          - (1.0 - p.prob_at_least_one_hr)
      END AS expected_value_per_unit,
      bo.fetched_at AS odds_fetched_at,
      ds.game_start_utc,
      bp.full_name AS batter_name,
      bp.bats AS batter_bats,
      bp.primary_position AS batter_position,
      pp.full_name AS pitcher_name,
      pp.throws AS pitcher_throws,
      pk.name AS park_name,
      mf.b_barrel_pct_season,
      mf.b_p90_ev_season,
      mf.park_hr_factor_hand,
      mf.p_hr_per_9_season,
      mf.p_barrel_pct_allowed_season,
      mf.ctx_batting_order,
      mf.ctx_projected_pa,
      mf.wx_wind_carry_cf,
      mf.wx_temperature_f,
      mf.wx_air_density_relative,
      COALESCE(
        tm_batter.abbr,
        CASE
          WHEN mf.ctx_is_home IS TRUE THEN tm_home.abbr
          WHEN mf.ctx_is_home IS FALSE THEN tm_away.abbr
          ELSE NULL
        END
      ) AS team_abbr,
      tm_home.abbr AS home_abbr,
      tm_away.abbr AS away_abbr
    FROM predictions p
    LEFT JOIN daily_schedule ds ON ds.game_pk = p.game_pk
    LEFT JOIN parks pk ON pk.park_id = ds.venue_id
    LEFT JOIN players bp ON bp.mlbam_id = p.batter_id
    LEFT JOIN players pp ON pp.mlbam_id = p.pitcher_id
    LEFT JOIN LATERAL (
      SELECT pl.team_id
      FROM projected_lineups pl
      WHERE pl.game_pk = p.game_pk
        AND pl.batter_id = p.batter_id
      ORDER BY pl.is_confirmed DESC, pl.fetched_at DESC NULLS LAST, pl.batting_order ASC
      LIMIT 1
    ) batter_lineup ON TRUE
    LEFT JOIN teams tm_batter ON tm_batter.team_id = batter_lineup.team_id
    LEFT JOIN teams tm_home ON tm_home.team_id = ds.home_team_id
    LEFT JOIN teams tm_away ON tm_away.team_id = ds.away_team_id
    LEFT JOIN matchup_features mf
      ON mf.game_pk = p.game_pk
     AND mf.batter_id = p.batter_id
     AND mf.pitcher_id = p.pitcher_id
     AND mf.game_date = p.game_date
    LEFT JOIN best_odds bo
      ON bo.game_pk = p.game_pk
     AND bo.batter_id = p.batter_id
    WHERE p.game_date = ${targetDate}
      AND p.model_version = ${modelVersion}
      AND p.prob_at_least_one_hr >= ${minProb}
      AND (
        ${team}::text IS NULL
        OR COALESCE(
          tm_batter.abbr,
          CASE
            WHEN mf.ctx_is_home IS TRUE THEN tm_home.abbr
            WHEN mf.ctx_is_home IS FALSE THEN tm_away.abbr
            ELSE NULL
          END
        ) = UPPER(${team}::text)
      )
    ORDER BY
      CASE WHEN ${sortByEhr} THEN p.expected_hrs
           ELSE p.prob_at_least_one_hr END DESC NULLS LAST,
      p.prob_at_least_one_hr DESC NULLS LAST,
      COALESCE(
        NULLIF(p.matchup_components->>'starter_raw_prob', '')::double precision,
        p.prob_at_least_one_hr
      ) DESC NULLS LAST,
      mf.ctx_projected_pa DESC NULLS LAST,
      mf.ctx_batting_order ASC NULLS LAST,
      p.batter_id ASC
    LIMIT ${limit}
  `) as unknown as Row[];
  return rows.map(toPick);
}

export async function picksToday(q: PicksQuery = {}): Promise<PickSummary[]> {
  const modelVersion = await activeModelVersion();
  if (!modelVersion) return [];

  const today = currentMlbDateString();
  const picks = await queryForDate(today, q, modelVersion);
  if (picks.length > 0) return picks;

  // Fallback: pick the most recent date that has predictions. Inference
  // runs locally on the user's machine and may lag by a day, especially
  // across the UTC date boundary.
  const [latest] = (await sql`
    SELECT MAX(game_date)::text AS d
    FROM predictions
    WHERE model_version = ${modelVersion}
  `) as unknown as { d: string | null }[];
  if (!latest?.d || latest.d === today) return picks;
  return queryForDate(latest.d, q, modelVersion);
}
