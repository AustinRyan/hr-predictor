import assert from "node:assert/strict";
import fs from "node:fs";

const nav = fs.readFileSync("components/landing/Nav.tsx", "utf8");
const css = fs.readFileSync("app/globals.css", "utf8");

assert.match(nav, /href="\/model"[\s\S]*>History</, "desktop nav must link History to /model");
assert.match(nav, /className="nav-history-link"[\s\S]*href="\/model"/, "collapsed nav must expose a /model history link");
assert.doesNotMatch(
  nav,
  /href="#(?:top|slate|how|model-audit|app)"/,
  "shared nav must use root-relative section links so /model nav clicks do not resolve under /model",
);
for (const section of ["slate", "how", "model-audit", "app"]) {
  assert.match(
    nav,
    new RegExp(`href="/#${section}"`),
    `nav section link ${section} must point back to the homepage`,
  );
}
assert.match(css, /\.nav-history-link\s*\{[\s\S]*display:\s*none/, "mobile history link must be hidden by default");
assert.match(
  css,
  /@media\s*\(max-width:\s*880px\)[\s\S]*\.nav-history-link\s*\{[\s\S]*display:\s*inline-flex/,
  "mobile history link must appear when desktop nav links collapse",
);

console.log("nav history link verification passed");
