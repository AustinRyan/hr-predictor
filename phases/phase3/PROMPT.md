# Phase 3 — Feature Engineering

## Required reading before you start
1. `./CLAUDE.md`
2. `./MASTER_PLAN.md` — Phase 3 section, especially the feature categories table
3. `./abstract.md` — should show Phases 0–2 complete
4. `./src/ingestion/overview.md` — understand source data
5. `./src/core/models.py` — schema
6. `./phases/phase1/NOTES.md`, `./phases/phase2/NOTES.md`

**Phase 3 is the most technically dense phase.** Read all physics and formula sections below carefully.

---

## Objective
Build the feature store. Every historical plate appearance and every upcoming PA gets a single wide feature row keyed by `(game_pk, batter_id, pitcher_id)`. All the features listed in MASTER_PLAN.md Phase 3 populated and correct.

**Scope boundary:** Feature computation only. No modeling. No predictions. Outputs land in `matchup_features` (materialized view or table, your call — document the decision).

---

## Deliverables

### 1. Schema additions (Alembic migration `0003_feature_store`)

Primary output table `matchup_features`:

Columns grouped by category. All numeric unless noted:

**Keys**
- `game_pk: int`, `batter_id: int`, `pitcher_id: int` — composite PK
- `game_date: date`
- `is_historical: bool` — True if this PA already happened (for training labels)
- `hr_on_pa: bool` nullable — the label, null for future PAs

**Batter rolling windows** (naming pattern: `b_{metric}_{window}` where window ∈ `7d`, `14d`, `30d`, `season`)
- `b_barrel_pct_7d`, `b_barrel_pct_14d`, `b_barrel_pct_30d`, `b_barrel_pct_season`
- `b_hardhit_pct_*`
- `b_avg_ev_*`
- `b_p90_ev_*` — 90th percentile exit velocity
- `b_avg_la_*`
- `b_sweet_spot_pct_*` — launch angle 8–32°
- `b_pulled_fb_pct_*`
- `b_xwobacon_*` — expected wOBA on contact
- `b_xiso_*`
- `b_hr_per_pa_*`
- `b_pa_count_*` — sample size in the window (important; early-season values need regression)

**Batter platoon splits**
- `b_vs_lhp_barrel_pct`, `b_vs_rhp_barrel_pct`
- `b_vs_lhp_xwoba`, `b_vs_rhp_xwoba`
- `b_vs_lhp_hr_per_pa`, `b_vs_rhp_hr_per_pa`
- `b_vs_lhp_pa_count`, `b_vs_rhp_pa_count` (for regression weights)

**Batter vs pitch-type** (2-season window)
- `b_xwoba_vs_ff`, `b_xwoba_vs_si`, `b_xwoba_vs_fc`, `b_xwoba_vs_sl`, `b_xwoba_vs_cu`, `b_xwoba_vs_ch`, `b_xwoba_vs_fs`
- `b_hr_rate_vs_ff`, `b_hr_rate_vs_sl`, ... (same pitch types)
- `b_pa_count_vs_ff`, ...

**Batter new-metric features (2024+; nullable for earlier)**
- `b_avg_bat_speed`
- `b_squared_up_pct`
- `b_blast_rate`

**Pitcher profile (season + career weighted)**
- `p_hr_per_9_season`, `p_hr_per_9_career`
- `p_barrel_pct_allowed_season`
- `p_hardhit_pct_allowed_season`
- `p_fb_pct`, `p_gb_pct`
- `p_k_pct`, `p_bb_pct`

**Pitcher handedness splits**
- `p_vs_lhb_xwoba_allowed`, `p_vs_rhb_xwoba_allowed`
- `p_vs_lhb_hr_rate`, `p_vs_rhb_hr_rate`

**Pitcher pitch mix & velocity**
- `p_ff_usage`, `p_si_usage`, `p_fc_usage`, `p_sl_usage`, `p_cu_usage`, `p_ch_usage`, `p_fs_usage`
- `p_ff_velo_avg` — average fastball velocity
- `p_primary_pitch: str` — most-used pitch type

**Pitcher context**
- `p_tto_penalty` — empirical HR-rate multiplier for projected time-through-order (see formula below)

**Bullpen team-level (for back half of game)**
- `bp_barrel_pct_allowed_season` — opposing team's bullpen aggregate
- `bp_hr_per_9_season`

**Park factors**
- `park_hr_factor_hand` — park HR factor for this batter's handedness this season
- `park_hr_factor_hand_3yr` — 3-year weighted
- `park_id: int`
- `park_elevation_ft: int`

**Weather**
- `wx_temperature_f`, `wx_humidity_pct`, `wx_pressure_hpa`
- `wx_air_density_relative` — computed (see formula below), 1.0 = average
- `wx_wind_speed_mph`
- `wx_wind_carry_lf`, `wx_wind_carry_cf`, `wx_wind_carry_rf` — projected wind assistance (+) or suppression (−) for balls hit to each field (see formula)
- `wx_is_roof_closed: bool` — gate feature; when true, all `wx_*` features above should equal climate-neutral baseline values

**Context**
- `ctx_batting_order: int`
- `ctx_projected_pa: float` — expected PAs for this batter in this game (based on batting order, roughly: slot 1 ≈ 4.6, slot 9 ≈ 3.7)
- `ctx_day_night: str` (D/N)
- `ctx_is_home: bool`
- `ctx_batter_days_rest: int`
- `ctx_pitcher_days_rest: int`
- `ctx_same_hand: bool` — True if same-handed matchup

### 2. Feature module structure under `src/features/`

- `src/features/batter_rolling.py` — rolling-window metrics
- `src/features/batter_splits.py` — platoon and pitch-type matrices
- `src/features/batter_tracking.py` — bat-tracking metrics (2024+ only)
- `src/features/pitcher_profile.py` — all pitcher features
- `src/features/pitcher_pitch_mix.py` — usage + velocity
- `src/features/bullpen.py` — team-level bullpen aggregates
- `src/features/park_factors.py` — join + weighting
- `src/features/weather_physics.py` — air density + wind vector (see formulas)
- `src/features/context.py` — PA projection, rest, day/night
- `src/features/builder.py` — orchestrator that assembles `matchup_features` rows
- `src/features/overview.md`

### 3. The physics — implement exactly as specified

#### Air density (relative)
```
T_k = (temperature_f + 459.67) * 5/9  # Fahrenheit to Kelvin
P_pa = pressure_hpa * 100
# Water vapor partial pressure (Magnus formula approximation)
e_sat = 611.2 * exp(17.67 * (T_k - 273.15) / (T_k - 29.65))
e = (humidity_pct / 100) * e_sat
# Density using ideal gas with humidity correction
rho = (P_pa - 0.378 * e) / (287.058 * T_k)
# Normalize against standard: 1.225 kg/m³ at sea level, 15°C, dry, 1013.25 hPa
wx_air_density_relative = rho / 1.225
```

Values near 0.93 (hot Coors day) mean lower density → more carry. Values near 1.05 (cold SF night) mean more drag → less carry.

#### Wind carry per field
Given `wind_direction_deg` (meteorological: direction FROM, measured clockwise from North), `wind_speed_mph`, and `park.orientation_deg` (bearing from home plate to CF, clockwise from North):

```python
import math

# Convert wind "from" direction to wind "to" direction (add 180°)
wind_to_deg = (wind_direction_deg + 180) % 360

# Park's outfield field lines (approximate)
# LF direction: park orientation - 45°
# CF direction: park orientation
# RF direction: park orientation + 45°
def wind_carry_component(field_bearing_deg, wind_to_deg, wind_speed_mph):
    # Angle between wind direction and field direction
    angle_diff = math.radians(wind_to_deg - field_bearing_deg)
    # Positive = wind blowing toward that field (carry-aiding)
    # Negative = wind blowing away (carry-suppressing)
    return wind_speed_mph * math.cos(angle_diff)

lf_bearing = (park_orientation_deg - 45) % 360
cf_bearing = park_orientation_deg
rf_bearing = (park_orientation_deg + 45) % 360

wx_wind_carry_lf = wind_carry_component(lf_bearing, wind_to_deg, wind_speed_mph)
wx_wind_carry_cf = wind_carry_component(cf_bearing, wind_to_deg, wind_speed_mph)
wx_wind_carry_rf = wind_carry_component(rf_bearing, wind_to_deg, wind_speed_mph)
```

Units: mph, signed. +15 means 15 mph of tailwind toward that field; −10 means 10 mph headwind suppressing it.

#### Roof-closed gating
When `daily_schedule.roof_status = 'closed'`:
- `wx_temperature_f = 72` (climate-controlled baseline)
- `wx_humidity_pct = 50`
- `wx_pressure_hpa = 1013.25`
- `wx_air_density_relative = 1.0`
- `wx_wind_speed_mph = 0`
- All `wx_wind_carry_*` = 0
- `wx_is_roof_closed = True`

### 4. Rolling-window computation

For each batter and each game_date, compute rolling aggregates over the prior N days (NOT including the current game — strictly prior, to avoid leakage).

Implementation suggestion: window functions in Postgres are cleaner than Python for this at scale. Write a materialized view `batter_rolling_features_mv` that's refreshed nightly.

Example for one metric:
```sql
SELECT
    batter,
    game_date,
    COUNT(*) FILTER (WHERE game_date > current_game_date - INTERVAL '7 days'
                     AND launch_speed_angle IN (6)) * 1.0 /
    NULLIF(COUNT(*) FILTER (WHERE game_date > current_game_date - INTERVAL '7 days'
                            AND launch_speed IS NOT NULL), 0) AS b_barrel_pct_7d,
    ...
```

(This is illustrative; write clean SQL using proper window frames.)

**Barrel definition in SQL:** Statcast labels barrels in `launch_speed_angle = 6`. Use that directly. Don't try to recompute the barrel formula from scratch.

**Leakage guarantee:** Feature rows for a PA on date D use only data strictly before date D. Write a test specifically asserting this (seed data with a clobber on date D, confirm the rolling feature on date D does not include it).

### 5. Platoon split regression

Raw rate `hr_per_pa_vs_lhp` with only 20 PA is unreliable. Regress toward league average:

```
regressed_rate = (observed_rate * pa_count + league_avg * regression_weight) / (pa_count + regression_weight)
```

Use `regression_weight = 100` as default (roughly a half-season of same-handed PAs). Store both `b_vs_lhp_hr_per_pa` (raw) and `b_vs_lhp_hr_per_pa_reg` (regressed). Model can use either; interpretability prefers regressed.

### 6. Projected PA by batting order

Hardcode these empirical averages from 2021–2024 data:

```python
PA_BY_BATTING_ORDER = {
    1: 4.60,
    2: 4.50,
    3: 4.40,
    4: 4.29,
    5: 4.19,
    6: 4.08,
    7: 3.97,
    8: 3.86,
    9: 3.75,
}
```

Document in code comment that these should be recomputed annually from `statcast_pitches`. Add a `TODO(phase4+)` comment.

### 7. Times-through-order penalty (pitcher)

Research consensus: 3rd TTO HR rate is ~20% higher than 1st TTO. Simplified formula:

```python
def tto_multiplier(projected_pa_number: int) -> float:
    """projected_pa_number = which plate appearance is this for the batter.
    1st PA (1st TTO) gets 1.0, 2nd PA gets ~1.05, 3rd PA gets ~1.20.
    If batter faces bullpen (4th PA+), we use bullpen features instead — return None."""
    if projected_pa_number <= 1: return 1.00
    if projected_pa_number == 2: return 1.05
    if projected_pa_number == 3: return 1.20
    return None  # bullpen territory
```

For feature building: compute expected starter PAs vs bullpen PAs based on projected PA count and expected starter innings. Store `p_tto_penalty` as the weighted average multiplier applied to starter portion.

### 8. Feature builder orchestration

`src/features/builder.py` entry point:

```python
def build_features_for_game(game_pk: int) -> int:
    """Build matchup_features rows for all batter-pitcher matchups in this game.
    Returns number of rows written."""

def build_features_for_historical(start_date: date, end_date: date) -> int:
    """Backfill feature rows for all historical PAs in date range."""

def build_features_for_today() -> int:
    """Convenience: build features for all games in daily_schedule for today."""
```

Historical backfill strategy:
- Iterate day by day
- For each game, for each PA, compute feature row using only data strictly prior
- Batch insert into `matchup_features`
- Idempotent upsert

### 9. Tests

- `tests/features/test_weather_physics.py` — unit tests for `wind_carry_component` with known inputs:
  - Wind from west (270°) into a park oriented north (0°) should aid LF (+), neutral CF, suppress RF (−)
  - Wind speed 0 returns all zeros
  - Roof closed gating produces all baseline values
- `tests/features/test_leakage.py` — seed known data, verify no future leak
- `tests/features/test_rolling.py` — synthetic batter with known HR dates, verify rolling counts
- `tests/features/test_platoon_regression.py` — small sample regresses hard toward mean

### 10. Phase docs

- `phases/phase3/ACCEPTANCE.md`
- `phases/phase3/NOTES.md`
- Populate `src/features/overview.md` thoroughly

---

## Acceptance checklist

```markdown
# Phase 3 — Acceptance Checklist

## Schema
- [ ] `0003_feature_store` migration applies cleanly, reversible
- [ ] `matchup_features` table exists with all documented columns
- [ ] Indexes on `(game_pk, game_date)`, `(batter_id, game_date)` present

## Historical backfill
- [ ] Backfill script runs for 2021–2024 without error
- [ ] Coverage: `SELECT COUNT(*) FROM matchup_features WHERE is_historical` ≥ 600k (roughly; depends on exact PAs)
- [ ] No-leak test passes: a feature row for game on 2022-07-04 uses no data from 2022-07-04 or later

## Physics sanity checks
- [ ] Wind from 270° (west) at 15 mph, park oriented 0° (CF is north): wind-TO is 90° (east). LF bearing = 315° (NW), RF bearing = 45° (NE). Expected: `wx_wind_carry_lf ≈ -10.6` (suppresses LF), `wx_wind_carry_rf ≈ +10.6` (aids RF), `wx_wind_carry_cf ≈ 0` (perpendicular). Tolerance ±0.5.
- [ ] Wind directly out to CF (blowing toward CF direction) at 10 mph produces `wx_wind_carry_cf ≈ +10` with LF and RF both `≈ +7` (cos 45° component)
- [ ] Wind speed 0 → all carry components 0
- [ ] Air density at 95°F, 60% humidity, 1013 hPa, sea level: ~0.96 (less than standard — thinner air)
- [ ] Air density at 40°F, 40% humidity, 1013 hPa: ~1.07 (denser — more drag)
- [ ] Coors Field on a warm day produces the lowest air_density_relative values (thinner air + elevation)

## Feature sanity checks
- [ ] Aaron Judge's feature row for a recent game has `b_barrel_pct_season` > 0.18
- [ ] A weak-contact hitter (pick one with <5 HRs in 2024) has `b_barrel_pct_season` < 0.05
- [ ] A lefty power hitter at Yankee Stadium has `park_hr_factor_hand` > 108
- [ ] Coors Field HR factor is max across the league
- [ ] `b_vs_lhp_hr_per_pa_reg` with low PA count is close to league average (regression working)

## Roof gating
- [ ] Tropicana Field games have `wx_is_roof_closed=True` always, all `wx_wind_carry_*` = 0
- [ ] Toronto Rogers Centre during a closed-roof game has baseline weather features
- [ ] Toronto during an open-roof game has actual weather values

## Tests
- [ ] `uv run pytest tests/features -v` all pass
- [ ] Coverage ≥80% on `src/features/`

## Docs
- [ ] `src/features/overview.md` documents each module, formulas, known gotchas
- [ ] `abstract.md` shows Phase 3 complete, Phase 4 pending
```

---

## Non-negotiables

- **No future leakage.** Ever. Explicit test for this.
- **All physics formulas implemented with unit tests** covering known conditions.
- **Nulls handled deliberately.** Document exactly what happens when a batter has <X PAs in a window (regression? null? league average?).
- **Idempotent feature builder.** Re-running produces same rows.
- **Partitioned or indexed for speed.** Feature builds over 4 seasons should complete in <30 min on a laptop.

---

## Post-phase ritual

1. `uv run pytest -q` → green
2. Run full historical backfill
3. Walk through acceptance checklist
4. Update `abstract.md`, `src/features/overview.md`
5. Commit + tag `phase-3-complete`

---

## STOP condition

Do not begin Phase 4 (modeling) without user approval. Report:
1. Row count in `matchup_features` per season
2. Physics sanity-check results
3. Any formula adjustments or defaults you made (document in `NOTES.md`)
