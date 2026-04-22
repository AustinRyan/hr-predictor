# Phase 2 — Implementation Notes

Mid-phase deviations from `PLAN.md` / `PROMPT.md`, plus per-source
quirks captured while the code was being written. The next person to
refresh any of these sources should re-verify the assumptions in each
section below.

---

## Park factors — source switch from CSV to HTML-embedded JSON

### What changed

`PLAN.md` specified a CSV endpoint at

```
https://baseballsavant.mlb.com/leaderboard/statcast-park-factors
    ?type=batter&bat_side={L|R}&year={season}&csv=true
```

That endpoint does **not** exist as a CSV. Appending `csv=true` returns
the full HTML page (Savant's "Download CSV" button is a client-side
JavaScript operation — there is no server-side CSV route for the
handedness-split leaderboard). Earlier fixtures checked into the repo
with a `.csv` extension were HTML and the parser would have failed on
first use.

### What we ship

Same URL path, different query params, HTML response parsed via an
embedded `var data = [...];` JavaScript literal:

```
https://baseballsavant.mlb.com/leaderboard/statcast-park-factors
    ?batSide={L|R}&year={season}&type=year&rolling=1
```

Key parameter quirks (locked-in assumptions — re-verify on refresh):

| Param | Value | Notes |
|---|---|---|
| `batSide` | `L` / `R` | **camelCase** — `bat_side` is silently ignored and the server falls back to "All" |
| `year` | e.g. `2024` | ignored unless paired with `type=year` |
| `type` | `year` | other options (`venue`, `distance`, `raw`) change the payload shape; we depend on `year` |
| `rolling` | `1` | selects single-season; omitting (or any value other than `1`) defaults to the 3-year rolling view |
| `venue` | (not used) | UI-only filter; the `var data` array contains all 30 parks regardless of `venue` |

Data shape (per-park row inside the JSON array):

```json
{
  "venue_id": "19",          // matches StatsAPI venue id (primary key for parks)
  "venue_name": "Coors Field",
  "key_bat_side": "R",
  "key_year": "2024",
  "key_num_years_rolling": "1",
  "key_is_year_rolling": "0",
  "n_pa": "10456",           // sample size
  "index_hr": "107",         // 100 = league average; see _METRIC_COLUMNS
  "index_runs": "125",
  "index_woba": "112",
  "index_hits": "118",
  "index_1b": "118",
  "index_2b": "119",
  "index_3b": "184",
  "index_hardhit": "100",
  "index_wobacon": "112",
  "index_xwobacon": "101",
  "index_bacon": "113",
  "index_xbacon": "102",
  "index_obp": "111",
  "index_so": "90",
  "index_bb": "99",
  "year_range": "2024"
}
```

`venue_id` is StatsAPI venue id (cross-referenced 2024 R-side — all 30
Savant venue IDs are a strict subset of the seeded `parks` table). No
name-lookup fallback is needed.

### Coverage and spot-checks at fixture capture (2026-04-22)

Fixture: `tests/ingestion/fixtures/savant_park_factors_{L,R}_2024.html`

- 30 rows per handedness, all 30 primary MLB parks present
- Coors Field (venue_id=19) 2024 single-season: **R HR = 107**, **L HR = 102**
- Yankee Stadium (venue_id=3313) 2024 single-season: **R HR = 129**, **L HR = 113**

Historical context that did **not** hold at this capture: the
often-quoted "Coors RHB HR > 110" figure is a 3-year rolling value.
Single-season figures fluctuate year-to-year. The regression guard in
`test_park_factors.py` asserts `Coors R HR > 100` (above league average)
and `Yankee R HR > 110` (short right-field porch makes this very stable).

### Things to re-verify when refreshing the source

1. The `var data = [...]` literal still exists on the page (a single
   regex covers extraction; if Savant switches to a fetch-style SPA,
   the entire parser needs to change).
2. The query parameters above still behave as specified. If Savant
   normalizes `batSide` → `bat_side` or flips `rolling` defaults, the
   fetcher needs updates.
3. `venue_id` still matches StatsAPI venue id.
4. `_METRIC_COLUMNS` keys still exist (Savant occasionally adds or
   renames indices; missing columns are silently skipped by the parser
   but will reduce row counts).
5. Two HTTP calls per season (one per handedness) still cover all 30
   parks. If Savant starts paginating, the plan changes.

### Rejected alternatives

- **Option A (`bat_side=All` single-index):** rejected upstream — the
  schema enforces `batter_handedness IN ('L', 'R')`.
- **Option C (FanGraphs):** not needed — Option B (Savant) worked.
- **`pybaseball.statcast_single_game_park_factor` / `park_factor`:**
  pitcher-oriented in current `pybaseball` releases; no batter-handedness
  split.
