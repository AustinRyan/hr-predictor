/**
 * Data-access layer for server components.
 *
 * Before: these functions fetched from the FastAPI backend at
 * NEXT_PUBLIC_API_URL. On Vercel we don't want a separate hosted
 * backend, so the implementations now query Postgres directly. The
 * user's laptop still runs inference and writes predictions into the
 * same Neon DB the deployed frontend reads.
 *
 * Call sites (page.tsx, player/[id]/page.tsx, matchup/.../page.tsx,
 * model/page.tsx) are unchanged — the function signatures preserve the
 * T | null contract so callers fall back to empty states on DB errors.
 */

import type {
  MatchupDetail,
  ModelMetricsResponse,
  PickSummary,
  PlayerDetail,
} from "./types";
import { matchupDetail as queryMatchup } from "./queries/matchup";
import { modelMetrics as queryModelMetrics } from "./queries/model";
import { picksToday as queryPicksToday } from "./queries/picks";
import { playerDetail as queryPlayer } from "./queries/player";

export type PicksQuery = {
  limit?: number;
  minProb?: number;
  team?: string;
  sort?: "prob" | "expected_hrs";
};

async function safe<T>(fn: () => Promise<T>): Promise<T | null> {
  try {
    return await fn();
  } catch (err) {
    console.error("DB query failed:", err);
    return null;
  }
}

export async function getPicksToday(q: PicksQuery = {}): Promise<PickSummary[] | null> {
  return safe(() => queryPicksToday(q));
}

export async function getPlayer(mlbamId: number): Promise<PlayerDetail | null> {
  return safe(() => queryPlayer(mlbamId));
}

export async function getMatchup(
  gamePk: number,
  batterId: number,
): Promise<MatchupDetail | null> {
  return safe(() => queryMatchup(gamePk, batterId));
}

export async function getModelMetrics(): Promise<ModelMetricsResponse | null> {
  return safe(() => queryModelMetrics());
}
