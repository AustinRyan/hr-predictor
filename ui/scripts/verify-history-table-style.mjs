import assert from "node:assert/strict";
import fs from "node:fs";

const component = fs.readFileSync("components/model/HistoryTable.tsx", "utf8");
const css = fs.readFileSync("app/globals.css", "utf8");

function assertCssDeclaration(selector, declaration, message) {
  const blocks = css.matchAll(/([^{}]+)\{([^{}]+)\}/g);
  for (const [, selectorText, body] of blocks) {
    const selectors = selectorText.split(",").map((value) => value.trim());
    if (selectors.includes(selector) && declaration.test(body)) return;
  }
  assert.fail(message);
}

for (const className of [
  "history-table-player",
  "history-player-main",
  "history-player-meta",
  "history-result-pill",
  "history-money-pill",
  "history-date-cell",
  "history-row-hit",
  "history-row-miss",
]) {
  assert.match(component, new RegExp(`className=.*${className}`), `${className} is missing from HistoryTable`);
}

assert.match(css, /@media\s*\(max-width:\s*760px\)[\s\S]*\.history-table[\s\S]*display:\s*block/, "mobile history table must switch out of raw table layout");
assert.match(css, /\.history-table\s+td\s*\{[\s\S]*white-space:\s*nowrap/, "history table cells must prevent date/number wrapping");
assert.match(css, /\.history-table-player\s*\{[\s\S]*white-space:\s*normal/, "player cells must allow controlled multiline content");
assertCssDeclaration(".history-table tr.history-row-hit td", /background\s*:/, "hit rows must get a full-row highlight");
assertCssDeclaration(".history-table tr.history-row-hit", /box-shadow\s*:/, "mobile hit cards must get an unmistakable highlight");
assertCssDeclaration(".history-result-pill", /border\s*:/, "result values must render as styled pills");
assertCssDeclaration(".history-money-pill", /border\s*:/, "unit values must render as styled pills");
assert.match(css, /\.history-table-summary\s*>\s*div\s*\{[\s\S]*min-height:\s*72px/, "summary cells need stable visual height");

console.log("history table style verification passed");
