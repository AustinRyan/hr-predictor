import assert from "node:assert/strict";
import { parseBoardEdge, sortPicksForBoard } from "../lib/ranking-sort.ts";

function pick(id, prob, edge, gamePk, team = "TST") {
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
    edge,
    ctx: [],
    gamePk,
  };
}

const rows = [
  pick(1, 14, "+1.0", 101, "ATL"),
  pick(2, 8, "+6.5", 102, "NYY"),
  pick(3, 10, "+3.0", 101, "ATL"),
];

assert.equal(parseBoardEdge("+6.5"), 6.5);
assert.equal(parseBoardEdge("LIFT +2.4"), 2.4);
assert.equal(parseBoardEdge("EDGE -1.2"), -1.2);
assert.equal(parseBoardEdge("n/a"), Number.NEGATIVE_INFINITY);

assert.deepEqual(
  sortPicksForBoard(rows, {
    sort: "edge",
    minProb: 0,
    team: "",
    limit: 10,
    onePerGame: false,
  }).map((row) => row.id),
  [2, 3, 1],
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

console.log("ranking sort verification passed");
