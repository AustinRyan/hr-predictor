/**
 * Shape adapter: API PickSummary → design Pick.
 *
 * The design was mocked with richer fields than the backend currently
 * returns (jersey number, book edge). For fields the backend doesn't own,
 * we synthesize sensible placeholders. The fields that ARE populated
 * (handedness, position, season barrel%, season EV90, park factor) come
 * straight from the players table + matchup_features row that drove
 * this prediction.
 */

import type { CtxChip, Pick as DesignPick } from "./mock-data";
import type { PickSummary } from "./types";

function splitName(
  full: string | null,
  batterId: number,
): { first: string; last: string } {
  // Missing batter in players table → render MLBAM id so "—" doesn't
  // appear (this happens for players the ingestion hasn't yet seeded,
  // e.g. recent signings from NPB).
  if (!full) return { first: "BATTER", last: `#${batterId}` };
  const up = full.toUpperCase().trim();
  const parts = up.split(/\s+/);
  if (parts.length === 1) return { first: "", last: parts[0] };
  return { first: parts[0], last: parts.slice(1).join(" ") };
}

function formatTime(utc: string | null): string {
  if (!utc) return "TBD";
  try {
    const d = new Date(utc);
    return d
      .toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
        timeZoneName: "short",
      })
      .toUpperCase();
  } catch {
    return "TBD";
  }
}

function formatEdge(expectedHrs: number | null, prob: number): string {
  // No book odds in v1 — "edge" is a cosmetic delta vs the ~4.65% base rate.
  const delta = expectedHrs !== null ? prob * 100 - 4.65 : prob * 100 - 4.65;
  const sign = delta >= 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)}`;
}

/**
 * Build three concrete stat chips per pick: barrel rate, 90th-pct exit
 * velocity, and park factor. These come straight from matchup_features
 * so a user can actually interpret them (vs. the raw SHAP contributions
 * we showed earlier, which were unreadable and sometimes duplicated
 * when the top-3 features clustered in one family like 30d/season EV).
 */
function ctxFromStats(p: PickSummary): CtxChip[] {
  const chips: CtxChip[] = [];

  if (p.barrel_pct_season !== null) {
    const pct = p.barrel_pct_season * 100;
    chips.push({
      k: "BRL",
      v: `${pct.toFixed(0)}%`,
      pos: pct >= 10,
      neg: pct < 5,
    });
  }
  if (p.p90_ev_season !== null) {
    chips.push({
      k: "EV90",
      v: p.p90_ev_season.toFixed(0),
      pos: p.p90_ev_season >= 106,
      neg: p.p90_ev_season < 100,
    });
  }
  if (p.park_hr_factor_hand !== null) {
    const d = p.park_hr_factor_hand - 100;
    const sign = d >= 0 ? "+" : "";
    chips.push({
      k: "PARK",
      v: `${sign}${d.toFixed(0)}`,
      pos: d > 3,
      neg: d < -3,
    });
  }
  return chips;
}

function normalizeHand(bats: string | null): "L" | "R" | "S" {
  const b = (bats ?? "").trim().toUpperCase();
  if (b === "L" || b === "R" || b === "S") return b;
  return "R";
}

export function adaptPickSummary(p: PickSummary): DesignPick {
  const { first, last } = splitName(p.batter_name, p.batter_id);
  const edgeStr = formatEdge(p.expected_hrs, p.prob_at_least_one_hr);
  const edgeNeg = edgeStr.startsWith("-");
  return {
    id: p.batter_id,
    first,
    last,
    // Jersey numbers aren't in our players table yet — 0 signals "unknown"
    // to Hero which hides the portrait-number in that case.
    num: 0,
    team: p.team_abbr ?? "—",
    pos: p.batter_position ?? "—",
    hand: normalizeHand(p.batter_bats),
    vs: (p.pitcher_name ?? "TBD").toUpperCase(),
    vsTeam: "",
    park: (p.park_name ?? "—").toUpperCase(),
    time: formatTime(p.game_start_utc),
    prob: p.prob_at_least_one_hr * 100,
    ehr: p.expected_hrs ?? 0,
    edge: edgeStr,
    neg: edgeNeg || undefined,
    ctx: ctxFromStats(p),
    gamePk: p.game_pk,
  };
}

export function adaptPicksList(picks: readonly PickSummary[]): DesignPick[] {
  return picks.map(adaptPickSummary);
}

/**
 * Extra fields that the hero card shows but the base design Pick type
 * doesn't carry (season barrel%, EV90, park factor). Returned alongside
 * the adapted pick so Hero can render real values when available.
 */
export type HeroStats = {
  barrelPct: number | null; // 0..1
  p90Ev: number | null; // mph
  parkFactor: number | null; // 100 = neutral
};

export function extractHeroStats(p: PickSummary): HeroStats {
  return {
    barrelPct: p.barrel_pct_season,
    p90Ev: p.p90_ev_season,
    parkFactor: p.park_hr_factor_hand,
  };
}
