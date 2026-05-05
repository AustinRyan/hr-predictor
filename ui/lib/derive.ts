/**
 * Derive game-level + ticker data from the real /picks/today payload.
 * Avoids a second round-trip — we already fetched every batter's pick,
 * which implicitly carries the game roster once we group by game_pk.
 */

import type { PickSummary, ModelMetricsResponse } from "./types";
import type { ScoreboardGame, SlateCard } from "./pick-view";
import { formatModelProbability } from "./probability-format";

function fmtTime(utc: string | null): string {
  if (!utc) return "TBD";
  try {
    const d = new Date(utc);
    return d
      .toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      })
      .replace(/\s*(AM|PM)/i, "");
  } catch {
    return "TBD";
  }
}

function shortName(full: string | null, batterId: number): string {
  if (!full) return `#${batterId}`;
  const parts = full.trim().split(/\s+/);
  const last = parts[parts.length - 1] ?? "";
  const firstInit = parts.length > 1 ? `${parts[0]!.charAt(0)}.` : "";
  return `${firstInit} ${last}`.trim().toUpperCase();
}

type GameGroup = {
  game_pk: number;
  time_utc: string | null;
  home: string | null;
  away: string | null;
  park: string | null;
  top: PickSummary;
};

function comparePickRank(a: PickSummary, b: PickSummary): number {
  const probDelta = b.prob_at_least_one_hr - a.prob_at_least_one_hr;
  if (probDelta !== 0) return probDelta;
  const rawDelta =
    (b.model_rank_score ?? b.prob_at_least_one_hr) -
    (a.model_rank_score ?? a.prob_at_least_one_hr);
  if (rawDelta !== 0) return rawDelta;
  return a.batter_id - b.batter_id;
}

/** Group picks by game_pk; track the highest-ranked batter per game. */
function groupGames(picks: readonly PickSummary[]): GameGroup[] {
  const map = new Map<number, GameGroup>();
  for (const p of picks) {
    const existing = map.get(p.game_pk);
    if (!existing) {
      map.set(p.game_pk, {
        game_pk: p.game_pk,
        time_utc: p.game_start_utc,
        home: p.home_team_abbr,
        away: p.away_team_abbr,
        park: p.park_name,
        top: p,
      });
    } else if (comparePickRank(p, existing.top) < 0) {
      existing.top = p;
    }
  }
  return [...map.values()].sort((a, b) => {
    const ta = a.time_utc ? new Date(a.time_utc).getTime() : Number.MAX_SAFE_INTEGER;
    const tb = b.time_utc ? new Date(b.time_utc).getTime() : Number.MAX_SAFE_INTEGER;
    return ta - tb;
  });
}

export function buildScoreboard(picks: readonly PickSummary[]): ScoreboardGame[] {
  return groupGames(picks).map((g) => ({
    away: g.away ?? "—",
    home: g.home ?? "—",
    time: fmtTime(g.time_utc),
    topProb: `${shortName(g.top.batter_name, g.top.batter_id)} · ${formatModelProbability(g.top.prob_at_least_one_hr)}`,
  }));
}

export function buildSlate(picks: readonly PickSummary[]): SlateCard[] {
  return groupGames(picks).map((g) => ({
    time: fmtTime(g.time_utc),
    away: g.away ?? "—",
    home: g.home ?? "—",
    park: (g.park ?? "—").toUpperCase(),
    // Weather not exposed on PickSummary yet — show the park factor +/-
    // which IS in scope and more actionable than raw wind anyway.
    windText:
      g.top.park_hr_factor_hand === null
        ? "—"
        : (() => {
            const d = g.top.park_hr_factor_hand - 100;
            const sign = d >= 0 ? "+" : "";
            return `${sign}${d.toFixed(0)}`;
          })(),
    tempText: "—",
    parkText:
      g.top.park_hr_factor_hand === null
        ? "—"
        : (() => {
            const d = g.top.park_hr_factor_hand - 100;
            const sign = d >= 0 ? "+" : "";
            return `${sign}${d.toFixed(0)}`;
          })(),
    topPick: `${shortName(g.top.batter_name, g.top.batter_id)} · ${formatModelProbability(g.top.prob_at_least_one_hr)}`,
  }));
}

/**
 * Build a rotating ticker of real facts pulled from the prediction set
 * and the production model's training metadata.
 */
export function buildTicker(
  picks: readonly PickSummary[],
  metrics: ModelMetricsResponse | null,
): string[] {
  const items: string[] = [];

  if (picks.length > 0) {
    const sorted = [...picks].sort(comparePickRank);
    const top = sorted[0]!;
    const topName = (top.batter_name ?? `#${top.batter_id}`).toUpperCase();
    items.push(`HR LEADER TODAY · ${topName} ${formatModelProbability(top.prob_at_least_one_hr)}`);
    items.push(
      `SLATE · ${new Set(picks.map((p) => p.game_pk)).size} GAMES · ${picks.length} QUALIFIED HITTERS`,
    );

    const edgeCount = picks.filter(
      (p) => p.prob_at_least_one_hr * 100 - 4.65 >= 2,
    ).length;
    if (edgeCount > 0) {
      items.push(`EDGE > +2.0 · ${edgeCount} PLAYS`);
    }

    // Highest park factor in today's slate
    const parks = picks
      .filter((p) => p.park_hr_factor_hand !== null)
      .sort(
        (a, b) => (b.park_hr_factor_hand ?? 0) - (a.park_hr_factor_hand ?? 0),
      );
    if (parks.length > 0) {
      const pk = parks[0]!;
      const d = (pk.park_hr_factor_hand ?? 100) - 100;
      const sign = d >= 0 ? "+" : "";
      items.push(
        `PARK FACTOR · ${(pk.park_name ?? "—").toUpperCase()} ${sign}${d.toFixed(0)}`,
      );
    }
  }

  if (metrics) {
    const brier = metrics.training_metrics.test_brier;
    const ece = metrics.training_metrics.test_ece;
    items.push(`MODEL ${metrics.training_metadata.model_version}`);
    if (brier !== null) {
      items.push(`BRIER TEST · ${brier.toFixed(4)}`);
    }
    if (ece !== null) {
      items.push(`CALIBRATION ECE · ${ece.toFixed(4)}`);
    }
  }

  if (items.length === 0) {
    items.push("LOADING MODEL OUTPUT…");
  }
  return items;
}

/**
 * Count of unique games on today's slate (for the hero strip + ticker).
 */
export function countGames(picks: readonly PickSummary[]): number {
  return new Set(picks.map((p) => p.game_pk)).size;
}
