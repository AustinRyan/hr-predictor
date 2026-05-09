import assert from "node:assert/strict";
import { adaptPickSummary } from "../lib/adapters.ts";
import { formatBoardProbability } from "../lib/probability-format.ts";
import { parseBoardEdge, sortPicksForBoard } from "../lib/ranking-sort.ts";

function pick(id, prob, edge, gamePk, team = "TST", rankScore = prob / 100, bookOdds) {
  return {
    id,
    first: "TEST",
    last: String(id),
    num: 0,
    team,
    pos: "DH",
    hand: "R",
    vs: "PITCHER",
    vsTeam: "OPP",
    park: "PARK",
    time: "7:00 PM",
    prob,
    ehr: prob / 100,
    rankScore,
    edge,
    edgeLabel: bookOdds ? "EDGE" : "LIFT",
    bookOdds,
    ctx: [],
    gamePk,
  };
}

const rows = [
  pick(1, 14, "+1.0", 101, "ATL", 0.14, "DK +500"),
  pick(2, 8, "+6.5", 102, "NYY", 0.08, "FD +800"),
  pick(3, 10, "+3.0", 101, "ATL", 0.1),
];

assert.equal(parseBoardEdge("+6.5"), 6.5);
assert.equal(parseBoardEdge("LIFT +2.4"), 2.4);
assert.equal(parseBoardEdge("EDGE -1.2"), -1.2);
assert.equal(parseBoardEdge("n/a"), Number.NEGATIVE_INFINITY);
assert.equal(formatBoardProbability(11.58213), "11.582%");
assert.equal(formatBoardProbability(0), "0.000%");

assert.deepEqual(
  sortPicksForBoard(rows, {
    sort: "edge",
    minProb: 0,
    team: "",
    limit: 10,
    onePerGame: false,
  }).map((row) => row.id),
  [2, 1],
);

assert.deepEqual(
  sortPicksForBoard(rows, {
    sort: "prob",
    minProb: 0,
    team: "",
    limit: 10,
    onePerGame: true,
  }).map((row) => row.id),
  [1, 2],
);

assert.deepEqual(
  sortPicksForBoard(rows, {
    sort: "prob",
    minProb: 10,
    team: "",
    limit: 10,
    onePerGame: false,
  }).map((row) => row.id),
  [1, 3],
);

assert.deepEqual(
  sortPicksForBoard(rows, {
    sort: "prob",
    minProb: 0,
    team: "atl",
    limit: 10,
    onePerGame: false,
  }).map((row) => row.id),
  [1, 3],
);

assert.deepEqual(
  sortPicksForBoard(rows, {
    sort: "prob",
    minProb: 0,
    team: "",
    limit: 2,
    onePerGame: false,
  }).map((row) => row.id),
  [1, 3],
);

assert.deepEqual(
  sortPicksForBoard(
    [
      pick(4, 11.6, "+0.2", 104, "SEA", 0.13),
      pick(5, 11.6, "+0.2", 105, "SEA", 0.18),
    ],
    {
      sort: "prob",
      minProb: 0,
      team: "",
      limit: 10,
      onePerGame: false,
    },
  ).map((row) => row.id),
  [5, 4],
);

const adaptedFullGamePick = adaptPickSummary({
  batter_id: 99,
  batter_name: "Full Game Batter",
  batter_bats: "L",
  batter_position: "DH",
  team_abbr: "TST",
  game_pk: 999,
  game_date: "2026-05-09",
  game_start_utc: null,
  park_name: "Test Park",
  home_team_abbr: "TST",
  away_team_abbr: "OPP",
  pitcher_id: 199,
  pitcher_name: "Starter Arm",
  pitcher_throws: "R",
  prob_at_least_one_hr: 0.1234,
  expected_hrs: 0.13,
  model_rank_score: 0.11,
  probability_semantics: "full_game_hr",
  full_game_probability: 0.1234,
  starter_matchup_probability: 0.087,
  odds_bookmaker: null,
  odds_bookmaker_key: null,
  odds_price_american: null,
  odds_point: null,
  market_implied_probability: null,
  market_no_vig_probability: null,
  fair_odds_american: null,
  model_edge: null,
  expected_value_per_unit: null,
  odds_fetched_at: null,
  barrel_pct_season: 0.12,
  p90_ev_season: 107,
  park_hr_factor_hand: 103,
  pitcher_hr_per_9_season: 1.3,
  pitcher_barrel_pct_allowed_season: 0.1,
  batting_order: 3,
  projected_pas: 4.5,
  wind_carry_cf: 1.2,
  temperature_f: 76,
  air_density_relative: 0.97,
  opp_team_id: 9022,
  opp_bp_hr_per_pa_30d: 0.041,
  opp_bp_hr_per_pa_season: 0.033,
  opp_bp_barrel_pct_allowed_30d: 0.122,
  opp_bp_barrel_pct_allowed_season: 0.101,
  opp_bp_hardhit_pct_allowed_30d: 0.488,
  opp_bp_hardhit_pct_allowed_season: 0.451,
  opp_bp_lhb_hr_per_pa_season: 0.037,
  opp_bp_rhb_hr_per_pa_season: 0.029,
  opp_bp_pitches_last_3d: 142,
  top_contributing_features: [{ name: "opp_bp_hr_per_pa_30d", contribution: 0.04 }],
  model_version: "v_test",
});

const bullpenGroup = adaptedFullGamePick.factors?.find((group) => group.label === "BULLPEN");
assert.equal(bullpenGroup?.items.some((item) => item.label === "HR/PA" && item.value === "4.1%"), true);
const modelGroup = adaptedFullGamePick.factors?.find((group) => group.label === "MODEL");
assert.equal(modelGroup?.items.some((item) => item.label === "FULL" && item.value === "12.3%"), true);
assert.equal(modelGroup?.items.some((item) => item.label === "START" && item.value === "8.7%"), true);

console.log("ranking sort verification passed");
