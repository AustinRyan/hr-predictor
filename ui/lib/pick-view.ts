export type CtxChip = {
  k: string;
  v: string;
  pos?: boolean;
  neg?: boolean;
};

export type FactorTone = "up" | "down" | "neutral";

export type FactorItem = {
  label: string;
  value: string;
  tone?: FactorTone;
};

export type FactorGroup = {
  label: string;
  items: FactorItem[];
};

export type Pick = {
  id: number;
  first: string;
  last: string;
  num: number;
  team: string;
  pos: string;
  hand: "R" | "L" | "S";
  vs: string;
  vsTeam: string;
  park: string;
  time: string;
  prob: number;
  ehr: number;
  rankScore?: number;
  edge: string;
  edgeLabel?: string;
  bookOdds?: string;
  fairOdds?: string;
  ev?: string;
  neg?: boolean;
  ctx: CtxChip[];
  factors?: FactorGroup[];
  gamePk?: number;
};

export type ScoreboardGame = {
  away: string;
  home: string;
  time: string;
  topProb: string;
};

export type SlateCard = {
  time: string;
  away: string;
  home: string;
  park: string;
  windText: string;
  tempText: string;
  parkText: string;
  topPick: string;
};

/** MLB CDN headshot with size + query params that work with duotone CSS filters. */
export function headshotUrl(mlbamId: number): string {
  return `https://img.mlbstatic.com/mlb-photos/image/upload/w_426,q_auto/v1/people/${mlbamId}/headshot/67/current`;
}
