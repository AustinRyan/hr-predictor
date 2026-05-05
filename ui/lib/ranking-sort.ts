import type { Pick } from "./pick-view";

export type SortKey = "prob" | "ehr" | "edge";

export type BoardSortOptions = {
  sort: SortKey;
  minProb: number;
  team: string;
  limit: number;
  onePerGame: boolean;
};

export function parseBoardEdge(edge: string): number {
  const match = edge.match(/[+-]?\d+(?:\.\d+)?/);
  if (!match) return Number.NEGATIVE_INFINITY;
  const parsed = Number.parseFloat(match[0]);
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}

function compareBySort(sort: SortKey, a: Pick, b: Pick): number {
  const rankScoreDelta = (b.rankScore ?? b.prob) - (a.rankScore ?? a.prob);
  const stableDelta = a.id - b.id;

  if (sort === "prob") {
    const probDelta = b.prob - a.prob;
    if (probDelta !== 0) return probDelta;
    if (rankScoreDelta !== 0) return rankScoreDelta;
    return stableDelta;
  }
  if (sort === "ehr") {
    const ehrDelta = b.ehr - a.ehr;
    if (ehrDelta !== 0) return ehrDelta;
    if (rankScoreDelta !== 0) return rankScoreDelta;
    return stableDelta;
  }

  const edgeDelta = parseBoardEdge(b.edge) - parseBoardEdge(a.edge);
  if (edgeDelta !== 0 && Number.isFinite(edgeDelta)) return edgeDelta;
  const probDelta = b.prob - a.prob;
  if (probDelta !== 0) return probDelta;
  if (rankScoreDelta !== 0) return rankScoreDelta;
  return stableDelta;
}

function normalizeTeam(value: string): string {
  return value.trim().toUpperCase();
}

export function sortPicksForBoard(
  picks: readonly Pick[],
  options: BoardSortOptions,
): Pick[] {
  const selectedTeam = normalizeTeam(options.team);
  const rows = picks.filter(
    (p) =>
      p.prob >= options.minProb &&
      (selectedTeam === "" || normalizeTeam(p.team) === selectedTeam),
  );
  const sorted = [...rows].sort((a, b) => compareBySort(options.sort, a, b));

  if (!options.onePerGame) return sorted.slice(0, options.limit);

  const seen = new Set<number>();
  const diversified: Pick[] = [];
  for (const p of sorted) {
    const key = p.gamePk ?? -1;
    if (key === -1 || seen.has(key)) continue;
    seen.add(key);
    diversified.push(p);
  }
  return diversified.slice(0, options.limit);
}

export function boardSortLabel(sort: SortKey): string {
  if (sort === "prob") return "Probability";
  if (sort === "ehr") return "E[HR]";
  return "Model lift";
}
