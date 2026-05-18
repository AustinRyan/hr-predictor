import { sql } from "@/lib/db";
import type { PickHistoryItem, PickHistoryResponse, PickHistorySummary } from "@/lib/types";

type Row = {
  game_date: Date | string;
  game_pk: number;
  batter_id: number;
  pitcher_id: number;
  prob_at_least_one_hr: string;
  expected_hrs: string | null;
  model_rank_score: string | null;
  batter_name: string | null;
  pitcher_name: string | null;
  park_name: string | null;
  team_abbr: string | null;
  daily_rank: number;
  actual_hrs: number;
  odds_bookmaker: string | null;
  odds_price_american: number | null;
  market_implied_probability: string | null;
};

function isoDate(value: Date | string): string {
  return value instanceof Date ? value.toISOString().slice(0, 10) : String(value).slice(0, 10);
}

function n(value: string | number | null): number | null {
  return value === null ? null : Number(value);
}

function fairAmerican(probability: number): number | null {
  if (probability <= 0 || probability >= 1) return null;
  if (probability >= 0.5) return Math.round((-100 * probability) / (1 - probability));
  return Math.round((100 * (1 - probability)) / probability);
}

function settledProfit(actualHr: boolean, american: number | null): number | null {
  if (american === null) return null;
  if (!actualHr) return -1;
  return american > 0 ? american / 100 : 100 / Math.abs(american);
}

function toItem(row: Row): PickHistoryItem {
  const probability = Number(row.prob_at_least_one_hr);
  const odds = row.odds_price_american === null ? null : Number(row.odds_price_american);
  const market = n(row.market_implied_probability);
  const actualHrs = Number(row.actual_hrs ?? 0);
  const actualHr = actualHrs > 0;
  return {
    game_date: isoDate(row.game_date),
    daily_rank: Number(row.daily_rank),
    batter_id: Number(row.batter_id),
    batter_name: row.batter_name,
    team_abbr: row.team_abbr,
    game_pk: Number(row.game_pk),
    pitcher_id: Number(row.pitcher_id),
    pitcher_name: row.pitcher_name,
    park_name: row.park_name,
    prob_at_least_one_hr: probability,
    expected_hrs: n(row.expected_hrs),
    model_rank_score: n(row.model_rank_score),
    actual_hr: actualHr,
    actual_hrs: actualHrs,
    odds_bookmaker: row.odds_bookmaker,
    odds_price_american: odds,
    market_implied_probability: market,
    fair_odds_american: fairAmerican(probability),
    model_edge: market === null ? null : probability - market,
    settled_profit_units: settledProfit(actualHr, odds),
  };
}

function summary(items: PickHistoryItem[], days: number, limitPerDay: number): PickHistorySummary {
  const hits = items.filter((item) => item.actual_hr).length;
  const profits = items
    .map((item) => item.settled_profit_units)
    .filter((value): value is number => value !== null);
  return {
    days,
    limit_per_day: limitPerDay,
    picks: items.length,
    hits,
    hit_rate: items.length === 0 ? null : hits / items.length,
    expected_hits: items.reduce((total, item) => total + item.prob_at_least_one_hr, 0),
    picks_with_odds: profits.length,
    settled_profit_units: profits.length === 0 ? null : profits.reduce((a, b) => a + b, 0),
  };
}

export async function pickHistory(
  modelVersion: string,
  days = 7,
  limitPerDay = 10,
): Promise<PickHistoryResponse> {
  const rows = (await sql`
    WITH settled_games AS (
      SELECT DISTINCT game_pk
      FROM statcast_pitches
      WHERE game_date BETWEEN CURRENT_DATE - (${days} || ' days')::interval
                          AND CURRENT_DATE - INTERVAL '1 day'
    ),
    candidates AS (
      SELECT
        p.game_date,
        p.game_pk,
        p.batter_id,
        p.pitcher_id,
        p.prob_at_least_one_hr,
        p.expected_hrs,
        COALESCE(
          NULLIF(p.matchup_components->>'full_game_raw_prob', '')::double precision,
          NULLIF(p.matchup_components->>'starter_raw_prob', '')::double precision,
          p.prob_at_least_one_hr
        ) AS model_rank_score,
        ds.game_start_utc,
        COALESCE(bp.full_name, odds_name.player_name) AS batter_name,
        pp.full_name AS pitcher_name,
        pk.name AS park_name,
        COALESCE(
          tm_batter.abbr,
          CASE
            WHEN mf.ctx_is_home IS TRUE THEN tm_home.abbr
            WHEN mf.ctx_is_home IS FALSE THEN tm_away.abbr
            ELSE NULL
          END
        ) AS team_abbr,
        ROW_NUMBER() OVER (
          PARTITION BY p.game_date
          ORDER BY
            p.prob_at_least_one_hr DESC NULLS LAST,
            COALESCE(
              NULLIF(p.matchup_components->>'full_game_raw_prob', '')::double precision,
              NULLIF(p.matchup_components->>'starter_raw_prob', '')::double precision,
              p.prob_at_least_one_hr
            ) DESC NULLS LAST,
            mf.ctx_projected_pa DESC NULLS LAST,
            mf.ctx_batting_order ASC NULLS LAST,
            p.batter_id ASC
        ) AS daily_rank,
        (
          SELECT COUNT(*)::int
          FROM statcast_pitches sp_hr
          WHERE sp_hr.game_pk = p.game_pk
            AND sp_hr.batter = p.batter_id
            AND sp_hr.events = 'home_run'
        ) AS actual_hrs
      FROM predictions p
      JOIN settled_games sg ON sg.game_pk = p.game_pk
      LEFT JOIN daily_schedule ds ON ds.game_pk = p.game_pk
      LEFT JOIN parks pk ON pk.park_id = ds.venue_id
      LEFT JOIN players bp ON bp.mlbam_id = p.batter_id
      LEFT JOIN players pp ON pp.mlbam_id = p.pitcher_id
      LEFT JOIN LATERAL (
        SELECT os.player_name
        FROM odds_snapshots os
        WHERE os.game_pk = p.game_pk
          AND os.batter_id = p.batter_id
          AND os.market_key = 'batter_home_runs'
          AND os.outcome_name IN ('Over', 'Yes')
          AND (os.point IS NULL OR ABS(os.point - 0.5) < 0.000001)
          AND COALESCE(os.raw_outcome->>'name', '') !~*
            '^\\s*[2-9][0-9]*\\+\\s+home runs?\\s*$'
        ORDER BY os.fetched_at DESC, os.market_last_update DESC NULLS LAST, os.id DESC
        LIMIT 1
      ) odds_name ON TRUE
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
      WHERE p.game_date BETWEEN CURRENT_DATE - (${days} || ' days')::interval
                            AND CURRENT_DATE - INTERVAL '1 day'
        AND p.model_version = ${modelVersion}
    )
    SELECT
      c.*,
      bo.bookmaker_title AS odds_bookmaker,
      bo.price_american AS odds_price_american,
      bo.implied_probability AS market_implied_probability
    FROM candidates c
    LEFT JOIN LATERAL (
      SELECT os.bookmaker_title, os.price_american, os.implied_probability, os.fetched_at
      FROM odds_snapshots os
      WHERE os.game_pk = c.game_pk
        AND os.batter_id = c.batter_id
        AND os.market_key = 'batter_home_runs'
        AND os.outcome_name IN ('Over', 'Yes')
        AND (os.point IS NULL OR ABS(os.point - 0.5) < 0.000001)
        AND COALESCE(os.raw_outcome->>'name', '') !~*
          '^\\s*[2-9][0-9]*\\+\\s+home runs?\\s*$'
        AND (c.game_start_utc IS NULL OR os.fetched_at <= c.game_start_utc)
      ORDER BY os.price_american DESC, os.fetched_at DESC
      LIMIT 1
    ) bo ON TRUE
    WHERE c.daily_rank <= ${limitPerDay}
    ORDER BY c.game_date DESC, c.daily_rank ASC
  `) as unknown as Row[];

  const items = rows.map(toItem);
  const dates = items.map((item) => item.game_date).sort();
  return {
    model_version: modelVersion,
    evaluated_from: dates[0] ?? null,
    evaluated_to: dates[dates.length - 1] ?? null,
    summary: summary(items, days, limitPerDay),
    items,
  };
}
