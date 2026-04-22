"""Pitcher profile feature SQL generator + TTO penalty helpers.

Emits per-matchup aggregates computed from prior ``statcast_pitches``
rows for the given pitcher (``sp.pitcher = mk.pitcher_id``). Season
window = Jan 1 of reference year. Career window = up to 10 years back
from the reference date (to bound the join — no MLB pitcher in our
training window has >10 seasons of Statcast data).

HR/9 approximation: we lack per-PA out counts, so use the proxy
``COUNT(HR) / COUNT(PA) * 38.7`` where 38.7 ≈ 9 innings × 4.3 PAs/inning
(MLB league avg). This is a reasonable proxy — off by a few percent for
extreme K or walk pitchers. Documented as a known simplification in
``phases/phase3/NOTES.md``.

Handedness splits use ``sp.stand`` (batter handedness), not
``sp.p_throws``. A LHB facing a RHP has ``sp.stand = 'L'``.

TTO (times-through-order) helpers (pure Python) compute a weighted
average HR multiplier across a batter's projected starter PAs. The
caller multiplies this into the per-PA HR probability. Bullpen PAs
(4th+) are excluded — they get separate bullpen features.

Leakage contract: strict ``<`` on reference_date. No ``<=`` anywhere.
"""

from __future__ import annotations


def tto_multiplier(projected_pa_number: int) -> float | None:
    """Return the HR-rate multiplier for a given PA number (PROMPT § 7).

    - 1st PA (1st time-through-order) → 1.00
    - 2nd PA → 1.05
    - 3rd PA → 1.20
    - 4th+ PA → ``None`` (bullpen territory; caller uses bullpen features)

    PA numbers ≤ 1 are conservatively treated as 1st PA (returns 1.00)
    so callers passing 0 or negative values don't crash.
    """
    if projected_pa_number <= 1:
        return 1.00
    if projected_pa_number == 2:
        return 1.05
    if projected_pa_number == 3:
        return 1.20
    return None


def tto_penalty_for(projected_pa_count: float) -> float:
    """Weighted-average TTO multiplier across a batter's starter PAs.

    Given a projected PA count (e.g. 4.2), integer PAs 1..floor(pa) get
    full weight 1.0; the fractional leftover goes to PA floor(pa)+1 with
    weight equal to the fraction.

    Bullpen PAs (where ``tto_multiplier`` returns ``None``) are dropped
    — the caller uses bullpen features separately, so we only want the
    starter portion's average multiplier here.

    Example: projected_pa_count = 4.2
      PA 1: weight 1.0 × 1.00
      PA 2: weight 1.0 × 1.05
      PA 3: weight 1.0 × 1.20
      PA 4: weight 1.0 × None (bullpen, dropped)
      PA 5: weight 0.2 × None (bullpen, dropped)
      → average = (1.00 + 1.05 + 1.20) / 3 ≈ 1.0833
    """
    if projected_pa_count <= 0:
        return 1.0  # Nobody plays? Return neutral.

    full_pa = int(projected_pa_count)
    frac = projected_pa_count - full_pa

    total_weight = 0.0
    total_weighted = 0.0
    for pa_number in range(1, full_pa + 1):
        mult = tto_multiplier(pa_number)
        if mult is None:
            continue
        total_weight += 1.0
        total_weighted += mult

    if frac > 0:
        mult = tto_multiplier(full_pa + 1)
        if mult is not None:
            total_weight += frac
            total_weighted += frac * mult

    if total_weight == 0:
        return 1.0
    return total_weighted / total_weight


# ---------- SQL generator ----------

# Season window: Jan 1 of the reference year up to (but not including)
# the reference date.
_SEASON = (
    "sp.game_date >= DATE_TRUNC('year', mk.reference_date)::date "
    "AND sp.game_date < mk.reference_date"
)

# Career window: up to 10 years back. Bounds the join; real pitcher
# careers in our training window don't exceed this.
_CAREER = (
    "sp.game_date >= (mk.reference_date - INTERVAL '10 years')::date "
    "AND sp.game_date < mk.reference_date"
)


def pitcher_profile_sql() -> str:
    """Return the SELECT body of the ``pitcher_profile`` CTE.

    Expects an upstream CTE named ``matchup_keys`` with columns
    ``(game_pk INT, batter_id INT, pitcher_id INT, reference_date DATE)``.
    Outputs one row per key with 4 keys + 12 metric columns:

    - ``p_hr_per_9_season`` — season HR allowed per 9 innings (proxy,
      HR/PA × 38.7)
    - ``p_hr_per_9_career`` — same proxy over the 10-year career window
    - ``p_barrel_pct_allowed_season`` — barrels allowed / BIP, season
    - ``p_hardhit_pct_allowed_season`` — EV ≥ 95 / BIP, season
    - ``p_fb_pct`` — launch_angle > 25 / BIP, season
    - ``p_gb_pct`` — launch_angle < 10 / BIP, season
    - ``p_k_pct`` — strikeouts / PA, season
    - ``p_bb_pct`` — (walk|intent_walk) / PA, season
    - ``p_vs_lhb_xwoba_allowed`` — avg xwOBA vs LHB (stand='L'), season
    - ``p_vs_rhb_xwoba_allowed`` — avg xwOBA vs RHB (stand='R'), season
    - ``p_vs_lhb_hr_rate`` — HR/PA vs LHB, season
    - ``p_vs_rhb_hr_rate`` — HR/PA vs RHB, season

    Leakage contract: aggregates use only pitches where
    ``sp.game_date < mk.reference_date`` (strict inequality).
    """
    # Season-scoped predicates reused in many expressions.
    bip_season = f"({_SEASON} AND sp.launch_speed IS NOT NULL)"
    la_season = f"({_SEASON} AND sp.launch_angle IS NOT NULL)"
    pa_season = f"({_SEASON} AND sp.events IS NOT NULL AND sp.events <> '')"
    pa_career = f"({_CAREER} AND sp.events IS NOT NULL AND sp.events <> '')"

    # Season HR/9 proxy: COUNT(HR) / COUNT(PA) * 38.7.
    hr_per_9_season = (
        f"(COUNT(*) FILTER (WHERE {_SEASON} AND sp.events = 'home_run')::float"
        f" / NULLIF(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
        f" FILTER (WHERE {pa_season})::float, 0)) * 38.7"
        " AS p_hr_per_9_season"
    )
    # Career HR/9 proxy: same formula over the career window.
    hr_per_9_career = (
        f"(COUNT(*) FILTER (WHERE {_CAREER} AND sp.events = 'home_run')::float"
        f" / NULLIF(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
        f" FILTER (WHERE {pa_career})::float, 0)) * 38.7"
        " AS p_hr_per_9_career"
    )

    # Barrel% allowed (season): barrels / BIP.
    barrel_pct_allowed = (
        f"(COUNT(*) FILTER (WHERE {_SEASON} AND sp.launch_speed_angle = 6)::float"
        f" / NULLIF(COUNT(*) FILTER (WHERE {bip_season})::float, 0))"
        " AS p_barrel_pct_allowed_season"
    )
    # Hard-hit% allowed (season): EV >= 95 / BIP.
    hardhit_pct_allowed = (
        f"(COUNT(*) FILTER (WHERE {_SEASON} AND sp.launch_speed >= 95)::float"
        f" / NULLIF(COUNT(*) FILTER (WHERE {bip_season})::float, 0))"
        " AS p_hardhit_pct_allowed_season"
    )
    # FB% (season): launch_angle > 25 / BIP (by launch_angle presence).
    fb_pct = (
        f"(COUNT(*) FILTER (WHERE {_SEASON} AND sp.launch_angle > 25)::float"
        f" / NULLIF(COUNT(*) FILTER (WHERE {la_season})::float, 0))"
        " AS p_fb_pct"
    )
    # GB% (season): launch_angle < 10 / BIP.
    gb_pct = (
        f"(COUNT(*) FILTER (WHERE {_SEASON} AND sp.launch_angle < 10)::float"
        f" / NULLIF(COUNT(*) FILTER (WHERE {la_season})::float, 0))"
        " AS p_gb_pct"
    )
    # K% (season): strikeouts / PA.
    k_pct = (
        f"(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
        f" FILTER (WHERE {_SEASON} AND sp.events LIKE 'strikeout%')::float"
        f" / NULLIF(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
        f" FILTER (WHERE {pa_season})::float, 0))"
        " AS p_k_pct"
    )
    # BB% (season): (walk|intent_walk) / PA.
    bb_pct = (
        f"(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
        f" FILTER (WHERE {_SEASON} AND sp.events IN ('walk', 'intent_walk'))::float"
        f" / NULLIF(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
        f" FILTER (WHERE {pa_season})::float, 0))"
        " AS p_bb_pct"
    )

    # Handedness splits: sp.stand is batter's stand, not pitcher's throws.
    hand_exprs: list[str] = []
    for stand, suffix in [("L", "lhb"), ("R", "rhb")]:
        pa_hand = (
            f"({_SEASON} AND sp.stand = '{stand}' "
            f"AND sp.events IS NOT NULL AND sp.events <> '')"
        )
        xw_hand = (
            f"({_SEASON} AND sp.stand = '{stand}' "
            f"AND sp.estimated_woba_using_speedangle IS NOT NULL)"
        )
        hand_exprs.append(
            f"AVG(sp.estimated_woba_using_speedangle) FILTER (WHERE {xw_hand})"
            f" AS p_vs_{suffix}_xwoba_allowed"
        )
        hand_exprs.append(
            f"(COUNT(*) FILTER (WHERE {_SEASON} AND sp.stand = '{stand}' "
            f"AND sp.events = 'home_run')::float"
            f" / NULLIF(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
            f" FILTER (WHERE {pa_hand})::float, 0))"
            f" AS p_vs_{suffix}_hr_rate"
        )

    parts: list[str] = [
        "mk.game_pk",
        "mk.batter_id",
        "mk.pitcher_id",
        "mk.reference_date",
        hr_per_9_season,
        hr_per_9_career,
        barrel_pct_allowed,
        hardhit_pct_allowed,
        fb_pct,
        gb_pct,
        k_pct,
        bb_pct,
        *hand_exprs,
    ]
    select_list = ",\n        ".join(parts)

    # Outer join bound to the career window so the join is finite even
    # when the season filter knocks all rows out.
    return f"""
    SELECT
        {select_list}
    FROM matchup_keys mk
    LEFT JOIN statcast_pitches sp
      ON sp.pitcher = mk.pitcher_id
     AND sp.game_date < mk.reference_date
     AND sp.game_date >= (mk.reference_date - INTERVAL '10 years')::date
    GROUP BY mk.game_pk, mk.batter_id, mk.pitcher_id, mk.reference_date
    """
