import type { PickHistoryItem } from "./types";

export type DailyExpectedActualPoint = {
  date: string;
  expectedHits: number;
  actualHits: number;
  picks: number;
};

export type CumulativeUnitsPoint = {
  date: string;
  label: string;
  units: number;
  cumulativeUnits: number;
};

export type DailyUnitSummary = {
  date: string;
  picks: number;
  hits: number;
  expectedHits: number;
  picksWithOdds: number;
  settledProfitUnits: number | null;
};

export type RankBand = {
  minRank: number;
  maxRank: number;
  label: string;
};

export type RankBandCalibrationPoint = {
  label: string;
  count: number;
  expectedRate: number;
  actualRate: number;
};

const DEFAULT_RANK_BANDS: readonly RankBand[] = [
  { minRank: 1, maxRank: 3, label: "#1-3" },
  { minRank: 4, maxRank: 7, label: "#4-7" },
  { minRank: 8, maxRank: 10, label: "#8-10" },
];

function rounded(value: number, decimals = 6): number {
  return Number(value.toFixed(decimals));
}

function compareHistoryItems(a: PickHistoryItem, b: PickHistoryItem): number {
  if (a.game_date !== b.game_date) return a.game_date.localeCompare(b.game_date);
  if (a.daily_rank !== b.daily_rank) return a.daily_rank - b.daily_rank;
  return a.batter_id - b.batter_id;
}

export function uniqueHistoryItems(items: readonly PickHistoryItem[]): PickHistoryItem[] {
  const byKey = new Map<string, PickHistoryItem>();
  for (const item of items) {
    const key = `${item.game_date}:${item.game_pk}:${item.batter_id}`;
    const existing = byKey.get(key);
    if (!existing || item.daily_rank < existing.daily_rank) {
      byKey.set(key, item);
    }
  }
  return [...byKey.values()].sort(compareHistoryItems);
}

export function filterHistoryByDate(
  items: readonly PickHistoryItem[],
  date: string | null,
): PickHistoryItem[] {
  const unique = uniqueHistoryItems(items);
  return date === null ? unique : unique.filter((item) => item.game_date === date);
}

export function buildDailyExpectedActual(
  items: readonly PickHistoryItem[],
): DailyExpectedActualPoint[] {
  const byDate = new Map<string, DailyExpectedActualPoint>();
  for (const item of uniqueHistoryItems(items)) {
    const current = byDate.get(item.game_date) ?? {
      date: item.game_date,
      expectedHits: 0,
      actualHits: 0,
      picks: 0,
    };
    current.expectedHits += item.prob_at_least_one_hr;
    current.actualHits += item.actual_hr ? 1 : 0;
    current.picks += 1;
    byDate.set(item.game_date, current);
  }

  return [...byDate.values()]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((point) => ({
      ...point,
      expectedHits: rounded(point.expectedHits),
    }));
}

export function buildDailyUnitSummaries(
  items: readonly PickHistoryItem[],
): DailyUnitSummary[] {
  const byDate = new Map<string, DailyUnitSummary>();
  for (const item of uniqueHistoryItems(items)) {
    const current = byDate.get(item.game_date) ?? {
      date: item.game_date,
      picks: 0,
      hits: 0,
      expectedHits: 0,
      picksWithOdds: 0,
      settledProfitUnits: null,
    };
    current.picks += 1;
    current.hits += item.actual_hr ? 1 : 0;
    current.expectedHits += item.prob_at_least_one_hr;
    if (item.settled_profit_units !== null) {
      current.picksWithOdds += 1;
      current.settledProfitUnits =
        (current.settledProfitUnits ?? 0) + item.settled_profit_units;
    }
    byDate.set(item.game_date, current);
  }

  return [...byDate.values()]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((summary) => ({
      ...summary,
      expectedHits: rounded(summary.expectedHits),
      settledProfitUnits:
        summary.settledProfitUnits === null
          ? null
          : rounded(summary.settledProfitUnits),
    }));
}

export function buildCumulativeUnits(
  items: readonly PickHistoryItem[],
): CumulativeUnitsPoint[] {
  let running = 0;
  return uniqueHistoryItems(items)
    .filter((item) => item.settled_profit_units !== null)
    .map((item) => {
      const units = item.settled_profit_units ?? 0;
      running += units;
      return {
        date: item.game_date,
        label: `${item.game_date} #${item.daily_rank}`,
        units: rounded(units),
        cumulativeUnits: rounded(running),
      };
    });
}

export function buildRankBandCalibration(
  items: readonly PickHistoryItem[],
  bands: readonly RankBand[] = DEFAULT_RANK_BANDS,
): RankBandCalibrationPoint[] {
  const unique = uniqueHistoryItems(items);
  return bands.map((band) => {
    const rows = unique.filter(
      (item) => item.daily_rank >= band.minRank && item.daily_rank <= band.maxRank,
    );
    const count = rows.length;
    const expectedRate =
      count > 0
        ? rows.reduce((total, item) => total + item.prob_at_least_one_hr, 0) / count
        : 0;
    const actualRate =
      count > 0
        ? rows.reduce((total, item) => total + (item.actual_hr ? 1 : 0), 0) / count
        : 0;
    return {
      label: band.label,
      count,
      expectedRate: rounded(expectedRate),
      actualRate: rounded(actualRate),
    };
  });
}
