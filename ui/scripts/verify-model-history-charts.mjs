import assert from "node:assert/strict";
import {
  buildCumulativeUnits,
  buildDailyUnitSummaries,
  buildDailyExpectedActual,
  buildRankBandCalibration,
  filterHistoryByDate,
  uniqueHistoryItems,
} from "../lib/model-history-charts.ts";

function item(date, rank, prob, hit, units) {
  return {
    game_date: date,
    daily_rank: rank,
    batter_id: 1000 + rank,
    batter_name: `Batter ${rank}`,
    team_abbr: "TST",
    game_pk: Number(date.replaceAll("-", "")) + rank,
    pitcher_id: 2000 + rank,
    pitcher_name: `Pitcher ${rank}`,
    park_name: "Test Park",
    prob_at_least_one_hr: prob,
    expected_hrs: prob,
    model_rank_score: prob,
    actual_hr: hit,
    actual_hrs: hit ? 1 : 0,
    odds_bookmaker: units === null ? null : "Book",
    odds_price_american: units === null ? null : 500,
    market_implied_probability: units === null ? null : 0.167,
    fair_odds_american: Math.round((100 * (1 - prob)) / prob),
    model_edge: units === null ? null : prob - 0.167,
    settled_profit_units: units,
  };
}

const rows = [
  item("2026-05-02", 1, 0.12, true, 5),
  item("2026-05-02", 4, 0.08, false, -1),
  item("2026-05-01", 2, 0.1, false, -1),
  item("2026-05-01", 8, 0.06, true, null),
  item("2026-05-01", 8, 0.06, true, null),
];

const uniqueRows = uniqueHistoryItems(rows);

assert.equal(uniqueRows.length, 4);

assert.deepEqual(filterHistoryByDate(uniqueRows, "2026-05-02").map((row) => row.daily_rank), [1, 4]);
assert.deepEqual(filterHistoryByDate(uniqueRows, null).map((row) => row.daily_rank), [2, 8, 1, 4]);

assert.deepEqual(buildDailyExpectedActual(uniqueRows), [
  { date: "2026-05-01", expectedHits: 0.16, actualHits: 1, picks: 2 },
  { date: "2026-05-02", expectedHits: 0.2, actualHits: 1, picks: 2 },
]);

assert.deepEqual(buildDailyUnitSummaries(uniqueRows), [
  {
    date: "2026-05-01",
    picks: 2,
    hits: 1,
    expectedHits: 0.16,
    picksWithOdds: 1,
    settledProfitUnits: -1,
  },
  {
    date: "2026-05-02",
    picks: 2,
    hits: 1,
    expectedHits: 0.2,
    picksWithOdds: 2,
    settledProfitUnits: 4,
  },
]);

assert.deepEqual(buildCumulativeUnits(uniqueRows), [
  {
    date: "2026-05-01",
    label: "2026-05-01 #2",
    units: -1,
    cumulativeUnits: -1,
  },
  {
    date: "2026-05-02",
    label: "2026-05-02 #1",
    units: 5,
    cumulativeUnits: 4,
  },
  {
    date: "2026-05-02",
    label: "2026-05-02 #4",
    units: -1,
    cumulativeUnits: 3,
  },
]);

assert.deepEqual(buildRankBandCalibration(uniqueRows), [
  { label: "#1-3", count: 2, expectedRate: 0.11, actualRate: 0.5 },
  { label: "#4-7", count: 1, expectedRate: 0.08, actualRate: 0 },
  { label: "#8-10", count: 1, expectedRate: 0.06, actualRate: 1 },
]);

console.log("model history chart verification passed");
