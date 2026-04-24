/**
 * Homerun — mock slate data
 * Ported from phases/phase7/design-source/project/Homerun.html (inline data.js).
 * Will be superseded in Stage 4 by real /picks/today responses.
 */

export type CtxChip = {
  k: string;
  v: string;
  pos?: boolean;
  neg?: boolean;
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
  edge: string;
  neg?: boolean;
  ctx: CtxChip[];
  // Optional for mock data; populated on real picks so rows can link to
  // /matchup/[gamePk]/[batterId] for the full breakdown.
  gamePk?: number;
};

export type ScoreboardGame = {
  away: string;
  home: string;
  time: string;
  topProb: string;
};

export const TEAMS: readonly string[] = [
  "LAA","LAD","SF","SD","ATL","NYY","NYM","BOS","PHI","HOU",
  "SEA","TEX","TOR","CHC","STL","MIL","CIN","PIT","KC","DET",
  "MIN","CLE","BAL","TB","WSH","MIA","OAK","AZ","COL","CWS",
];

export const PICKS: readonly Pick[] = [
  { id: 545361, first: "MIKE", last: "TROUT", num: 27, team: "LAA", pos: "CF", hand: "R",
    vs: "MILES MIKOLAS", vsTeam: "STL", park: "BUSCH STADIUM", time: "7:45 PM CT",
    prob: 14.8, ehr: 0.178, edge: "+4.2",
    ctx: [{ k: "WIND", v: "+1.2", pos: true }, { k: "PARK", v: "+6", pos: true }, { k: "R/R", v: "NEU" }] },
  { id: 592450, first: "AARON", last: "JUDGE", num: 99, team: "NYY", pos: "RF", hand: "R",
    vs: "TYLER GLASNOW", vsTeam: "LAD", park: "YANKEE STADIUM", time: "7:05 PM ET",
    prob: 13.9, ehr: 0.162, edge: "+3.6",
    ctx: [{ k: "WIND", v: "+1.8", pos: true }, { k: "PARK", v: "+8", pos: true }, { k: "BVP", v: "HOT", pos: true }] },
  { id: 660670, first: "RONALD", last: "ACUÑA JR.", num: 13, team: "ATL", pos: "RF", hand: "R",
    vs: "CHRIS SALE", vsTeam: "BOS", park: "TRUIST PARK", time: "7:20 PM ET",
    prob: 12.6, ehr: 0.148, edge: "+2.9",
    ctx: [{ k: "WIND", v: "+0.6", pos: true }, { k: "PARK", v: "+3", pos: true }, { k: "HR/9", v: "1.42", pos: true }] },
  { id: 660271, first: "SHOHEI", last: "OHTANI", num: 17, team: "LAD", pos: "DH", hand: "L",
    vs: "GERRIT COLE", vsTeam: "NYY", park: "DODGER STADIUM", time: "10:10 PM ET",
    prob: 12.1, ehr: 0.141, edge: "+2.2",
    ctx: [{ k: "WIND", v: "0.0" }, { k: "PARK", v: "+4", pos: true }, { k: "L/R", v: "NEU" }] },
  { id: 656941, first: "KYLE", last: "SCHWARBER", num: 12, team: "PHI", pos: "LF", hand: "L",
    vs: "LOGAN WEBB", vsTeam: "SF", park: "CITIZENS BANK", time: "6:40 PM ET",
    prob: 11.4, ehr: 0.132, edge: "+3.1",
    ctx: [{ k: "WIND", v: "+1.4", pos: true }, { k: "PARK", v: "+7", pos: true }, { k: "HR/9", v: "1.10", pos: true }] },
  { id: 624413, first: "PETE", last: "ALONSO", num: 20, team: "NYM", pos: "1B", hand: "R",
    vs: "ZACK WHEELER", vsTeam: "PHI", park: "CITI FIELD", time: "7:10 PM ET",
    prob: 10.8, ehr: 0.124, edge: "+1.8",
    ctx: [{ k: "WIND", v: "-0.4", neg: true }, { k: "PARK", v: "-2", neg: true }, { k: "BVP", v: "COLD", neg: true }] },
  { id: 665742, first: "JUAN", last: "SOTO", num: 22, team: "NYY", pos: "RF", hand: "L",
    vs: "TYLER GLASNOW", vsTeam: "LAD", park: "YANKEE STADIUM", time: "7:05 PM ET",
    prob: 10.2, ehr: 0.118, edge: "+2.4",
    ctx: [{ k: "WIND", v: "+1.8", pos: true }, { k: "PARK", v: "+8", pos: true }, { k: "L/R", v: "+", pos: true }] },
  { id: 621566, first: "MATT", last: "OLSON", num: 28, team: "ATL", pos: "1B", hand: "L",
    vs: "CHRIS SALE", vsTeam: "BOS", park: "TRUIST PARK", time: "7:20 PM ET",
    prob: 9.7, ehr: 0.112, edge: "+1.4",
    ctx: [{ k: "WIND", v: "+0.6", pos: true }, { k: "PARK", v: "+3", pos: true }, { k: "L/L", v: "-", neg: true }] },
  { id: 606192, first: "TEOSCAR", last: "HERNÁNDEZ", num: 37, team: "LAD", pos: "LF", hand: "R",
    vs: "GERRIT COLE", vsTeam: "NYY", park: "DODGER STADIUM", time: "10:10 PM ET",
    prob: 9.3, ehr: 0.108, edge: "+0.9",
    ctx: [{ k: "WIND", v: "0.0" }, { k: "PARK", v: "+4", pos: true }, { k: "HR/9", v: "0.88" }] },
  { id: 547180, first: "BRYCE", last: "HARPER", num: 3, team: "PHI", pos: "1B", hand: "L",
    vs: "LOGAN WEBB", vsTeam: "SF", park: "CITIZENS BANK", time: "6:40 PM ET",
    prob: 8.9, ehr: 0.104, edge: "+1.1",
    ctx: [{ k: "WIND", v: "+1.4", pos: true }, { k: "PARK", v: "+7", pos: true }, { k: "L/R", v: "+", pos: true }] },
  { id: 677594, first: "JULIO", last: "RODRÍGUEZ", num: 44, team: "SEA", pos: "CF", hand: "R",
    vs: "FRAMBER VALDEZ", vsTeam: "HOU", park: "T-MOBILE PARK", time: "10:10 PM ET",
    prob: 8.4, ehr: 0.098, edge: "+0.5",
    ctx: [{ k: "WIND", v: "-0.6", neg: true }, { k: "PARK", v: "-4", neg: true }, { k: "BVP", v: "NEU" }] },
  { id: 596019, first: "FRANCISCO", last: "LINDOR", num: 12, team: "NYM", pos: "SS", hand: "S",
    vs: "ZACK WHEELER", vsTeam: "PHI", park: "CITI FIELD", time: "7:10 PM ET",
    prob: 8.0, ehr: 0.093, edge: "+0.3",
    ctx: [{ k: "WIND", v: "-0.4", neg: true }, { k: "PARK", v: "-2", neg: true }, { k: "S/R", v: "+", pos: true }] },
  { id: 665489, first: "VLADIMIR", last: "GUERRERO JR.", num: 27, team: "TOR", pos: "1B", hand: "R",
    vs: "TARIK SKUBAL", vsTeam: "DET", park: "ROGERS CENTRE", time: "7:07 PM ET",
    prob: 7.6, ehr: 0.088, edge: "+0.8",
    ctx: [{ k: "WIND", v: "DOME" }, { k: "PARK", v: "+2", pos: true }, { k: "HR/9", v: "1.02" }] },
  { id: 670541, first: "YORDAN", last: "ALVAREZ", num: 44, team: "HOU", pos: "DH", hand: "L",
    vs: "LOGAN GILBERT", vsTeam: "SEA", park: "MINUTE MAID", time: "8:10 PM CT",
    prob: 7.2, ehr: 0.084, edge: "-0.2", neg: true,
    ctx: [{ k: "WIND", v: "DOME" }, { k: "PARK", v: "+5", pos: true }, { k: "L/R", v: "+", pos: true }] },
  { id: 608070, first: "JOSÉ", last: "RAMÍREZ", num: 11, team: "CLE", pos: "3B", hand: "S",
    vs: "COREY KLUBER", vsTeam: "BOS", park: "PROGRESSIVE", time: "7:10 PM ET",
    prob: 6.8, ehr: 0.079, edge: "+0.1",
    ctx: [{ k: "WIND", v: "+0.4", pos: true }, { k: "PARK", v: "-1", neg: true }, { k: "S/R", v: "NEU" }] },
  { id: 518692, first: "FREDDIE", last: "FREEMAN", num: 5, team: "LAD", pos: "1B", hand: "L",
    vs: "GERRIT COLE", vsTeam: "NYY", park: "DODGER STADIUM", time: "10:10 PM ET",
    prob: 6.4, ehr: 0.075, edge: "-0.4", neg: true,
    ctx: [{ k: "WIND", v: "0.0" }, { k: "PARK", v: "+4", pos: true }, { k: "L/R", v: "NEU" }] },
  { id: 672275, first: "ELLY", last: "DE LA CRUZ", num: 44, team: "CIN", pos: "SS", hand: "S",
    vs: "PAUL SKENES", vsTeam: "PIT", park: "GREAT AMERICAN", time: "6:40 PM ET",
    prob: 6.1, ehr: 0.071, edge: "+0.6",
    ctx: [{ k: "WIND", v: "+2.0", pos: true }, { k: "PARK", v: "+11", pos: true }, { k: "HR/9", v: "0.72", neg: true }] },
  { id: 682998, first: "CORBIN", last: "CARROLL", num: 7, team: "AZ", pos: "LF", hand: "L",
    vs: "KEVIN GAUSMAN", vsTeam: "TOR", park: "CHASE FIELD", time: "9:40 PM ET",
    prob: 5.8, ehr: 0.068, edge: "-0.1",
    ctx: [{ k: "WIND", v: "DOME" }, { k: "PARK", v: "+3", pos: true }, { k: "L/R", v: "NEU" }] },
  { id: 663656, first: "KYLE", last: "TUCKER", num: 30, team: "HOU", pos: "RF", hand: "L",
    vs: "LOGAN GILBERT", vsTeam: "SEA", park: "MINUTE MAID", time: "8:10 PM CT",
    prob: 5.5, ehr: 0.064, edge: "+0.2",
    ctx: [{ k: "WIND", v: "DOME" }, { k: "PARK", v: "+5", pos: true }, { k: "L/R", v: "+", pos: true }] },
  { id: 571448, first: "NOLAN", last: "ARENADO", num: 28, team: "STL", pos: "3B", hand: "R",
    vs: "TYLER ANDERSON", vsTeam: "LAA", park: "BUSCH STADIUM", time: "7:45 PM CT",
    prob: 5.1, ehr: 0.060, edge: "-0.6", neg: true,
    ctx: [{ k: "WIND", v: "+1.2", pos: true }, { k: "PARK", v: "-2", neg: true }, { k: "R/L", v: "+", pos: true }] },
];

export const SCOREBOARD: readonly ScoreboardGame[] = [
  { away: "LAD", home: "NYY", time: "7:05", topProb: "J. SOTO · 10.2%" },
  { away: "BOS", home: "ATL", time: "7:20", topProb: "R. ACUÑA JR. · 12.6%" },
  { away: "SF",  home: "PHI", time: "6:40", topProb: "K. SCHWARBER · 11.4%" },
  { away: "PHI", home: "NYM", time: "7:10", topProb: "P. ALONSO · 10.8%" },
  { away: "LAA", home: "STL", time: "7:45", topProb: "M. TROUT · 14.8%" },
  { away: "DET", home: "TOR", time: "7:07", topProb: "V. GUERRERO JR. · 7.6%" },
  { away: "SEA", home: "HOU", time: "8:10", topProb: "Y. ÁLVAREZ · 7.2%" },
  { away: "PIT", home: "CIN", time: "6:40", topProb: "E. DE LA CRUZ · 6.1%" },
];

export const TICKER: readonly string[] = [
  "WIND +11 KC→LF AT CITIZENS BANK",
  "BULLPEN ALERT · NYY RP FATIGUE +.04",
  "MODEL UPDATE · v4.2.1 CALIBRATED",
  "HR LEADER TODAY · M. TROUT 14.8%",
  "SLATE · 15 GAMES · 412 QUALIFIED HITTERS",
  "PARK FACTOR · GREAT AMERICAN +11% RHB",
  "WEATHER · 78°F CLEAR AT BUSCH",
  "BVP SIGNAL · JUDGE vs GLASNOW 3/7 2HR",
  "BRIER 30D · .0043",
  "EDGE > +2.0 · 8 PLAYS",
];

/** MLB CDN headshot with size + query params that work (from the design). */
export function headshotUrl(mlbamId: number): string {
  return `https://img.mlbstatic.com/mlb-photos/image/upload/w_426,q_auto/v1/people/${mlbamId}/headshot/67/current`;
}

/** Slate cards — synthesized per-game from top pick per game_pk (via park + time). */
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

export const SLATE_CARDS: readonly SlateCard[] = [
  { time: "6:40 PM ET", away: "SF",  home: "PHI", park: "CITIZENS BANK", windText: "+11 LF", tempText: "74°", parkText: "+7", topPick: "K. SCHWARBER · 11.4%" },
  { time: "6:40 PM ET", away: "PIT", home: "CIN", park: "GREAT AMERICAN", windText: "+14 CF", tempText: "72°", parkText: "+11", topPick: "E. DE LA CRUZ · 6.1%" },
  { time: "7:05 PM ET", away: "LAD", home: "NYY", park: "YANKEE STADIUM", windText: "+8 RF", tempText: "68°", parkText: "+8", topPick: "A. JUDGE · 13.9%" },
  { time: "7:07 PM ET", away: "DET", home: "TOR", park: "ROGERS CENTRE", windText: "DOME", tempText: "—", parkText: "+2", topPick: "V. GUERRERO JR. · 7.6%" },
  { time: "7:10 PM ET", away: "PHI", home: "NYM", park: "CITI FIELD", windText: "-4 RF", tempText: "66°", parkText: "-2", topPick: "P. ALONSO · 10.8%" },
  { time: "7:10 PM ET", away: "BOS", home: "CLE", park: "PROGRESSIVE", windText: "+2 LF", tempText: "64°", parkText: "-1", topPick: "J. RAMÍREZ · 6.8%" },
  { time: "7:20 PM ET", away: "BOS", home: "ATL", park: "TRUIST PARK", windText: "+6 LF", tempText: "76°", parkText: "+3", topPick: "R. ACUÑA JR. · 12.6%" },
  { time: "7:45 PM CT", away: "LAA", home: "STL", park: "BUSCH STADIUM", windText: "+12 LF", tempText: "78°", parkText: "+6", topPick: "M. TROUT · 14.8%" },
  { time: "8:10 PM CT", away: "SEA", home: "HOU", park: "MINUTE MAID", windText: "DOME", tempText: "—", parkText: "+5", topPick: "Y. ÁLVAREZ · 7.2%" },
  { time: "9:40 PM ET", away: "KEV", home: "AZ",  park: "CHASE FIELD", windText: "DOME", tempText: "—", parkText: "+3", topPick: "C. CARROLL · 5.8%" },
  { time: "10:10 PM ET", away: "LAD", home: "SF", park: "ORACLE PARK", windText: "-9 LF", tempText: "58°", parkText: "-8", topPick: "M. YASTRZEMSKI · 4.1%" },
  { time: "10:10 PM ET", away: "HOU", home: "SEA", park: "T-MOBILE PARK", windText: "-6 CF", tempText: "58°", parkText: "-4", topPick: "J. RODRÍGUEZ · 8.4%" },
  { time: "10:10 PM ET", away: "NYY", home: "LAD", park: "DODGER STADIUM", windText: "0", tempText: "70°", parkText: "+4", topPick: "S. OHTANI · 12.1%" },
];
