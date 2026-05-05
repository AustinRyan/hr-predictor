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

import type { CtxChip, FactorGroup, FactorItem, Pick as DesignPick } from "./pick-view";
import type { FeatureContribution, PickSummary } from "./types";

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

function formatEdge(p: PickSummary): string {
  const delta =
    p.model_edge !== null
      ? p.model_edge * 100
      : p.expected_hrs !== null
        ? p.prob_at_least_one_hr * 100 - 4.65
        : p.prob_at_least_one_hr * 100 - 4.65;
  const sign = delta >= 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)}`;
}

function formatAmerican(value: number | null): string | null {
  if (value === null) return null;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value}`;
}

function fairAmericanFromProbability(probability: number): string {
  if (probability <= 0 || probability >= 1) return "—";
  if (probability >= 0.5) {
    return `${Math.round((-100 * probability) / (1 - probability))}`;
  }
  return `+${Math.round(100 * (1 - probability) / probability)}`;
}

function formatEv(value: number | null): string | null {
  if (value === null) return null;
  const sign = value >= 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)}%`;
}

function shortBookName(key: string | null, title: string | null): string | null {
  const raw = (key || title || "").trim().toUpperCase();
  if (!raw) return null;
  const known: Record<string, string> = {
    DRAFTKINGS: "DK",
    FANDUEL: "FD",
    BETMGM: "MGM",
    BETRIVERS: "RIVERS",
    CAESARS: "CZR",
  };
  return known[raw] ?? raw.slice(0, 7);
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

function factor(label: string, value: string | null, tone: FactorItem["tone"] = "neutral"): FactorItem | null {
  if (value === null || value === "NaN") return null;
  return { label, value, tone };
}

function compactNumber(value: number | null, digits = 1): string | null {
  return value === null ? null : value.toFixed(digits);
}

function pct(value: number | null, digits = 0): string | null {
  return value === null ? null : `${(value * 100).toFixed(digits)}%`;
}

function signedDelta(value: number | null, baseline: number, digits = 0): string | null {
  if (value === null) return null;
  const delta = value - baseline;
  const sign = delta >= 0 ? "+" : "";
  return `${sign}${delta.toFixed(digits)}`;
}

function toneFromDelta(value: number | null, baseline: number, threshold: number): FactorItem["tone"] {
  if (value === null) return "neutral";
  const delta = value - baseline;
  if (delta > threshold) return "up";
  if (delta < -threshold) return "down";
  return "neutral";
}

function toneFromContribution(value: number): FactorItem["tone"] {
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "neutral";
}

function formatContribution(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

function featureLabel(name: string): string {
  const exact: Record<string, string> = {
    b_barrel_pct_7d: "BRL 7D",
    b_barrel_pct_14d: "BRL 14D",
    b_barrel_pct_30d: "BRL 30D",
    b_barrel_pct_season: "BRL SEAS",
    b_p90_ev_7d: "EV90 7D",
    b_p90_ev_14d: "EV90 14D",
    b_p90_ev_30d: "EV90 30D",
    b_p90_ev_season: "EV90 SEAS",
    b_xiso_30d: "xISO 30D",
    b_xiso_season: "xISO SEAS",
    b_hr_per_pa_30d: "HR/PA 30D",
    b_hr_per_pa_season: "HR/PA SEAS",
    p_hr_per_9_season: "SP HR/9",
    p_barrel_pct_allowed_season: "SP BRL",
    p_ff_velo_avg: "SP FF Velo",
    p_tto_penalty: "TTO",
    bp_barrel_pct_allowed_season: "BP BRL",
    bp_hr_per_9_season: "BP HR/9",
    park_hr_factor_hand: "Park HR",
    park_hr_factor_hand_3yr: "Park 3Y",
    wx_temperature_f: "Temp",
    wx_air_density_relative: "Air",
    wx_wind_carry_cf: "Wind CF",
    wx_wind_carry_lf: "Wind LF",
    wx_wind_carry_rf: "Wind RF",
    ctx_batting_order: "Slot",
    ctx_projected_pa: "PA",
    ctx_is_home: "Home",
    ctx_same_hand: "Hand",
  };
  if (exact[name]) return exact[name];
  return name
    .replace(/^(b|p|bp|wx|ctx)_/, "")
    .replaceAll("_pct", "%")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function modelDriverFactors(features: FeatureContribution[]): FactorItem[] {
  return features.slice(0, 5).map((f) => ({
    label: featureLabel(f.name),
    value: formatContribution(f.contribution),
    tone: toneFromContribution(f.contribution),
  }));
}

function factorGroups(p: PickSummary): FactorGroup[] {
  const hand =
    p.batter_bats && p.pitcher_throws
      ? `${p.batter_bats.toUpperCase()}/${p.pitcher_throws.toUpperCase()}`
      : null;
  const edgeStr = formatEdge(p);
  const bookName = shortBookName(p.odds_bookmaker_key, p.odds_bookmaker);
  const bookOdds = formatAmerican(p.odds_price_american);
  const fairOdds =
    p.odds_price_american === null
      ? null
      : p.fair_odds_american !== null
        ? formatAmerican(p.fair_odds_american)
        : fairAmericanFromProbability(p.prob_at_least_one_hr);
  const ev = formatEv(p.expected_value_per_unit);
  const hasMarket = p.odds_price_american !== null && p.market_implied_probability !== null;
  const groups: FactorGroup[] = [
    {
      label: "MARKET",
      items: hasMarket
        ? [
            factor("EDGE", `${edgeStr} pt`, edgeStr.startsWith("-") ? "down" : "up"),
            factor("BOOK", bookOdds === null ? null : `${bookName ?? "BOOK"} ${bookOdds}`, "neutral"),
            factor("FAIR", fairOdds, "neutral"),
            factor("EV", ev, p.expected_value_per_unit !== null && p.expected_value_per_unit > 0 ? "up" : "down"),
            factor("IMP", pct(p.market_implied_probability, 1), "neutral"),
          ].filter((x): x is FactorItem => x !== null)
        : [],
    },
    {
      label: "BAT",
      items: [
        factor("BRL", pct(p.barrel_pct_season), (p.barrel_pct_season ?? 0) >= 0.1 ? "up" : "neutral"),
        factor("EV90", compactNumber(p.p90_ev_season, 0), (p.p90_ev_season ?? 0) >= 106 ? "up" : "neutral"),
        factor("EHR", compactNumber(p.expected_hrs, 3), "neutral"),
      ].filter((x): x is FactorItem => x !== null),
    },
    {
      label: "MATCH",
      items: [
        factor("SP HR/9", compactNumber(p.pitcher_hr_per_9_season, 2), (p.pitcher_hr_per_9_season ?? 0) >= 1.2 ? "up" : "neutral"),
        factor("SP BRL", pct(p.pitcher_barrel_pct_allowed_season, 1), (p.pitcher_barrel_pct_allowed_season ?? 0) >= 0.09 ? "up" : "neutral"),
        factor("HAND", hand, p.batter_bats && p.pitcher_throws && p.batter_bats === p.pitcher_throws ? "down" : "neutral"),
        factor("SLOT", p.batting_order === null ? null : `${p.batting_order}`, p.batting_order !== null && p.batting_order <= 4 ? "up" : "neutral"),
        factor("PA", compactNumber(p.projected_pas, 1), (p.projected_pas ?? 0) >= 4.4 ? "up" : "neutral"),
      ].filter((x): x is FactorItem => x !== null),
    },
    {
      label: "PARK/WX",
      items: [
        factor("PARK", signedDelta(p.park_hr_factor_hand, 100), toneFromDelta(p.park_hr_factor_hand, 100, 3)),
        factor("WIND CF", compactNumber(p.wind_carry_cf, 1), toneFromDelta(p.wind_carry_cf, 0, 1)),
        factor("TEMP", p.temperature_f === null ? null : `${p.temperature_f.toFixed(0)}F`, (p.temperature_f ?? 0) >= 75 ? "up" : "neutral"),
        factor("AIR", compactNumber(p.air_density_relative, 3), p.air_density_relative !== null && p.air_density_relative < 0.98 ? "up" : "neutral"),
      ].filter((x): x is FactorItem => x !== null),
    },
    {
      label: "MODEL",
      items: [
        factor("RAW", pct(p.model_rank_score, 1), "neutral"),
        ...modelDriverFactors(p.top_contributing_features),
      ].filter((x): x is FactorItem => x !== null),
    },
  ];
  return groups.filter((group) => group.items.length > 0);
}

export function adaptPickSummary(p: PickSummary): DesignPick {
  const { first, last } = splitName(p.batter_name, p.batter_id);
  const edgeStr = formatEdge(p);
  const edgeNeg = edgeStr.startsWith("-");
  const hasMarket = p.odds_price_american !== null;
  const bookName = shortBookName(p.odds_bookmaker_key, p.odds_bookmaker);
  const bookOdds = formatAmerican(p.odds_price_american);
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
    rankScore: (p.model_rank_score ?? p.prob_at_least_one_hr) * 100,
    edge: edgeStr,
    edgeLabel: hasMarket ? "EDGE" : "LIFT",
    bookOdds: hasMarket && bookOdds ? `${bookName ?? "BOOK"} ${bookOdds}` : undefined,
    fairOdds:
      hasMarket && p.fair_odds_american !== null
        ? formatAmerican(p.fair_odds_american) ?? undefined
        : hasMarket
          ? fairAmericanFromProbability(p.prob_at_least_one_hr)
          : undefined,
    ev: hasMarket ? formatEv(p.expected_value_per_unit) ?? undefined : undefined,
    neg: edgeNeg || undefined,
    ctx: ctxFromStats(p),
    factors: factorGroups(p),
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
