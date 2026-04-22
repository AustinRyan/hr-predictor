"""Feature-store builder: composes Phase 3 feature CTEs into INSERTs.

Entry points
------------
* :func:`build_features_for_game` — write rows for one game_pk.
* :func:`build_features_for_historical` — iterate day-by-day over a date range.
* :func:`build_features_for_today` — iterate daily_schedule for CURRENT_DATE.

Strategy
--------
One large SQL composition of every feature CTE + joins to ``games``,
``parks``, ``daily_schedule``, and latest ``weather_forecasts`` yields
raw per-matchup rows. A short Python post-processing pass then computes:

* weather physics (air density, wind carry, roof gating),
* park-factor lookups (per-handedness + 3-year weighted),
* context derivations (projected PA, day/night fallback, days rest,
  same-hand, TTO penalty).

The final dicts are batched into ``pg_insert(MatchupFeature)
.on_conflict_do_update(...)``, making reruns idempotent.

Known Phase 3 gaps (documented in ``phases/phase3/NOTES.md``)
-------------------------------------------------------------
* ``wx_*`` columns are NULL for historical rows — the Phase 2 weather
  table only collects forecasts for today/future parks.
* ``ctx_batting_order`` is NULL for historical rows — no
  ``projected_lineups`` exists for past games (Phase 4+ backfill).
* ``b_pulled_fb_pct_*`` is NULL: the batter_rolling CTE emits the
  literal ``NULL::double precision`` until hc_x/hc_y-based pull
  classification lands.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.db import get_engine
from src.core.models import MatchupFeature
from src.features.batter_rolling import rolling_features_sql
from src.features.batter_splits import pitch_type_matrix_sql, platoon_splits_sql
from src.features.batter_tracking import bat_tracking_sql
from src.features.bullpen import bullpen_sql
from src.features.context import (
    PA_BY_BATTING_ORDER,
    day_night_letter,
    days_since_last_game,
    same_hand,
)
from src.features.park_factors_features import (
    park_hr_factor_3yr_weighted,
    park_hr_factor_for,
)
from src.features.pitcher_pitch_mix import pitch_mix_sql
from src.features.pitcher_profile import pitcher_profile_sql, tto_penalty_for
from src.features.weather_physics import (
    air_density_relative,
    apply_roof_gating,
    wind_carry_components,
)

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column groups — enumerated explicitly to dodge ``br.*`` collisions across
# CTEs that all re-emit the (game_pk, batter_id, reference_date) keys.
# ---------------------------------------------------------------------------

_BATTER_ROLLING_COLS: tuple[str, ...] = tuple(
    f"b_{metric}_{window}"
    for window in ("7d", "14d", "30d", "season")
    for metric in (
        "barrel_pct",
        "hardhit_pct",
        "avg_ev",
        "p90_ev",
        "avg_la",
        "sweet_spot_pct",
        "xwobacon",
        "xiso",
        "hr_per_pa",
        "pa_count",
        "pulled_fb_pct",
    )
)

_BATTER_PLATOON_COLS: tuple[str, ...] = tuple(
    f"b_vs_{hand}_{metric}"
    for hand in ("lhp", "rhp")
    for metric in ("barrel_pct", "xwoba", "hr_per_pa", "hr_per_pa_reg", "pa_count")
)

_PITCH_TYPES: tuple[str, ...] = ("ff", "si", "fc", "sl", "cu", "ch", "fs")
_BATTER_PTM_COLS: tuple[str, ...] = tuple(
    f"b_{metric}_vs_{pt}" for pt in _PITCH_TYPES for metric in ("xwoba", "hr_rate", "pa_count")
)

_BATTER_BT_COLS: tuple[str, ...] = ("b_avg_bat_speed", "b_squared_up_pct", "b_blast_rate")

_PITCHER_PROFILE_COLS: tuple[str, ...] = (
    "p_hr_per_9_season",
    "p_hr_per_9_career",
    "p_barrel_pct_allowed_season",
    "p_hardhit_pct_allowed_season",
    "p_fb_pct",
    "p_gb_pct",
    "p_k_pct",
    "p_bb_pct",
    "p_vs_lhb_xwoba_allowed",
    "p_vs_lhb_hr_rate",
    "p_vs_rhb_xwoba_allowed",
    "p_vs_rhb_hr_rate",
)

_PITCH_MIX_COLS: tuple[str, ...] = tuple(f"p_{pt}_usage" for pt in _PITCH_TYPES) + (
    "p_ff_velo_avg",
    "p_primary_pitch",
)

_BULLPEN_COLS: tuple[str, ...] = ("bp_barrel_pct_allowed_season", "bp_hr_per_9_season")

# Columns that are pulled in by _run_feature_query but are NOT persisted to
# matchup_features — they feed the Python post-processing in _finalize_row.
_TRANSIENT_COLS: frozenset[str] = frozenset(
    {
        "park_orientation_deg",
        "park_roof_type",
        "ctx_day_night_raw",
        "game_start_utc",
        "wx_wind_direction_deg",
        "batter_stand",
        "pitcher_throws",
        "roof_status",
    }
)

# Valid MatchupFeature column names — the final upsert drops anything not
# in this set (guards against stray transients leaking into the INSERT).
_MATCHUP_FEATURE_COLS: frozenset[str] = frozenset(c.name for c in MatchupFeature.__table__.columns)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_features_for_game(game_pk: int, *, engine: Engine | None = None) -> int:
    """Build and upsert all (batter, pitcher) feature rows for one game.

    Returns the number of rows written (pre-dedup — equivalent to
    ``len(matchup_keys)``). A return value of 0 means no matchup keys
    could be derived (e.g. future game with no projected lineup).
    """
    engine = engine or get_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with session_factory() as s:
        is_historical = _detect_historical(s, game_pk)

        raw_rows = _run_feature_query(s, game_pk, is_historical)
        if not raw_rows:
            _log.info(
                "builder: no matchup rows",
                extra={"game_pk": game_pk, "is_historical": is_historical},
            )
            return 0

        final_rows: list[dict[str, Any]] = [
            _finalize_row(s, r, is_historical=is_historical) for r in raw_rows
        ]
        _upsert_rows(s, final_rows)
        s.commit()

    _log.info(
        "builder: wrote rows",
        extra={"game_pk": game_pk, "rows": len(final_rows), "is_historical": is_historical},
    )
    return len(final_rows)


def build_features_for_historical(
    start_date: date,
    end_date: date,
    *,
    engine: Engine | None = None,
) -> int:
    """Iterate day-by-day over a closed date range; build each day's games."""
    engine = engine or get_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    total = 0
    day = start_date
    while day <= end_date:
        with session_factory() as s:
            game_pks = (
                s.execute(
                    text("SELECT DISTINCT game_pk FROM statcast_pitches WHERE game_date = :d"),
                    {"d": day},
                )
                .scalars()
                .all()
            )

        for gpk in game_pks:
            total += build_features_for_game(gpk, engine=engine)

        day += timedelta(days=1)

    return total


def build_features_for_today(*, engine: Engine | None = None) -> int:
    """Iterate daily_schedule for CURRENT_DATE, build each game's features."""
    engine = engine or get_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with session_factory() as s:
        game_pks = (
            s.execute(text("SELECT game_pk FROM daily_schedule WHERE game_date = CURRENT_DATE"))
            .scalars()
            .all()
        )

    total = 0
    for gpk in game_pks:
        total += build_features_for_game(gpk, engine=engine)
    return total


# ---------------------------------------------------------------------------
# SQL composition
# ---------------------------------------------------------------------------


def _detect_historical(session: Session, game_pk: int) -> bool:
    """True iff any statcast_pitches rows exist for this game_pk."""
    return bool(
        session.execute(
            text("SELECT COUNT(*) > 0 FROM statcast_pitches WHERE game_pk = :gp"),
            {"gp": game_pk},
        ).scalar_one()
    )


def _matchup_keys_cte(*, is_historical: bool) -> str:
    if is_historical:
        return """
            SELECT DISTINCT
                sp.game_pk,
                sp.game_date AS reference_date,
                sp.batter AS batter_id,
                sp.pitcher AS pitcher_id
            FROM statcast_pitches sp
            WHERE sp.game_pk = :game_pk
        """
    return """
        SELECT
            ds.game_pk,
            ds.game_date AS reference_date,
            pl.batter_id,
            CASE WHEN pl.team_id = ds.home_team_id
                 THEN ds.probable_away_pitcher_id
                 ELSE ds.probable_home_pitcher_id END AS pitcher_id
        FROM daily_schedule ds
        JOIN projected_lineups pl ON pl.game_pk = ds.game_pk
        WHERE ds.game_pk = :game_pk
          AND (pl.team_id = ds.home_team_id OR pl.team_id = ds.away_team_id)
          AND CASE WHEN pl.team_id = ds.home_team_id
                   THEN ds.probable_away_pitcher_id
                   ELSE ds.probable_home_pitcher_id END IS NOT NULL
    """


def _qualified_cols(alias: str, cols: tuple[str, ...]) -> str:
    """Render ``alias.col AS col, ...`` — explicit enumeration to dodge
    collisions from ``alias.*`` when multiple CTEs re-emit key columns.
    """
    return ",\n        ".join(f"{alias}.{c} AS {c}" for c in cols)


def _run_feature_query(session: Session, game_pk: int, is_historical: bool) -> list[dict[str, Any]]:
    """Execute the composed CTE query and return raw per-matchup rows."""
    matchup_cte = _matchup_keys_cte(is_historical=is_historical)

    if is_historical:
        label_sql = (
            "EXISTS (SELECT 1 FROM statcast_pitches sp_hr "
            "WHERE sp_hr.game_pk = mk.game_pk AND sp_hr.batter = mk.batter_id "
            "AND sp_hr.pitcher = mk.pitcher_id AND sp_hr.events = 'home_run') AS hr_on_pa"
        )
        is_hist_literal = "TRUE"
    else:
        label_sql = "NULL::boolean AS hr_on_pa"
        is_hist_literal = "FALSE"

    # The daily_schedule join only makes sense for future games; for
    # historical we LEFT JOIN anyway (harmless — all NULLs).
    big_sql = f"""
    WITH matchup_keys AS (
        {matchup_cte}
    ),
    batter_rolling AS (
        {rolling_features_sql()}
    ),
    batter_platoon AS (
        {platoon_splits_sql()}
    ),
    batter_ptm AS (
        {pitch_type_matrix_sql()}
    ),
    batter_bt AS (
        {bat_tracking_sql()}
    ),
    pitcher_profile_cte AS (
        {pitcher_profile_sql()}
    ),
    pitcher_pm AS (
        {pitch_mix_sql()}
    ),
    bullpen_cte AS (
        {bullpen_sql()}
    )
    SELECT
        mk.game_pk,
        mk.reference_date AS game_date,
        mk.batter_id,
        mk.pitcher_id,
        {is_hist_literal} AS is_historical,
        {label_sql},
        {_qualified_cols('br', _BATTER_ROLLING_COLS)},
        {_qualified_cols('bp_pl', _BATTER_PLATOON_COLS)},
        {_qualified_cols('bp_pt', _BATTER_PTM_COLS)},
        {_qualified_cols('btk', _BATTER_BT_COLS)},
        {_qualified_cols('pp', _PITCHER_PROFILE_COLS)},
        {_qualified_cols('pm', _PITCH_MIX_COLS)},
        {_qualified_cols('bpn', _BULLPEN_COLS)},
        -- Park lookup (inline).
        COALESCE(g.venue_id, ds.venue_id) AS park_id,
        pk.elevation_ft AS park_elevation_ft,
        pk.orientation_deg AS park_orientation_deg,
        pk.roof_type AS park_roof_type,
        -- Context bits.
        g.day_night AS ctx_day_night_raw,
        ds.game_start_utc AS game_start_utc,
        -- Weather (latest fetched, if any).
        wf.temperature_f AS wx_temperature_f,
        wf.humidity_pct AS wx_humidity_pct,
        wf.pressure_hpa AS wx_pressure_hpa,
        wf.wind_speed_mph AS wx_wind_speed_mph,
        wf.wind_direction_deg AS wx_wind_direction_deg,
        -- Home/away classification (historical: via inning_topbot first pitch;
        -- future: via projected_lineups.team_id == home_team_id).
        CASE
            WHEN {is_hist_literal} THEN (
                SELECT CASE sp_ha.inning_topbot WHEN 'Bot' THEN TRUE ELSE FALSE END
                FROM statcast_pitches sp_ha
                WHERE sp_ha.game_pk = mk.game_pk
                  AND sp_ha.batter = mk.batter_id
                ORDER BY sp_ha.at_bat_number, sp_ha.pitch_number
                LIMIT 1
            )
            ELSE (pl_home.team_id IS NOT NULL)
        END AS ctx_is_home,
        -- Batting order (future only; historical stays NULL).
        pl_any.batting_order AS ctx_batting_order,
        -- Batter stand / pitcher throws (most recent observation; used for same_hand()).
        (
            SELECT sp_bs.stand FROM statcast_pitches sp_bs
            WHERE sp_bs.batter = mk.batter_id AND sp_bs.stand IS NOT NULL
            ORDER BY sp_bs.game_date DESC LIMIT 1
        ) AS batter_stand,
        (
            SELECT sp_pt.p_throws FROM statcast_pitches sp_pt
            WHERE sp_pt.pitcher = mk.pitcher_id AND sp_pt.p_throws IS NOT NULL
            ORDER BY sp_pt.game_date DESC LIMIT 1
        ) AS pitcher_throws,
        -- Player-table fallback for handedness (future games).
        pl_bat.bats AS batter_bats_fallback,
        pl_pit.throws AS pitcher_throws_fallback,
        -- Daily-schedule roof status.
        ds.roof_status AS roof_status
    FROM matchup_keys mk
    LEFT JOIN batter_rolling br
      ON br.game_pk = mk.game_pk AND br.batter_id = mk.batter_id
     AND br.reference_date = mk.reference_date
    LEFT JOIN batter_platoon bp_pl
      ON bp_pl.game_pk = mk.game_pk AND bp_pl.batter_id = mk.batter_id
     AND bp_pl.reference_date = mk.reference_date
    LEFT JOIN batter_ptm bp_pt
      ON bp_pt.game_pk = mk.game_pk AND bp_pt.batter_id = mk.batter_id
     AND bp_pt.reference_date = mk.reference_date
    LEFT JOIN batter_bt btk
      ON btk.game_pk = mk.game_pk AND btk.batter_id = mk.batter_id
     AND btk.reference_date = mk.reference_date
    LEFT JOIN pitcher_profile_cte pp
      ON pp.game_pk = mk.game_pk AND pp.batter_id = mk.batter_id
     AND pp.pitcher_id = mk.pitcher_id AND pp.reference_date = mk.reference_date
    LEFT JOIN pitcher_pm pm
      ON pm.game_pk = mk.game_pk AND pm.batter_id = mk.batter_id
     AND pm.pitcher_id = mk.pitcher_id AND pm.reference_date = mk.reference_date
    LEFT JOIN bullpen_cte bpn
      ON bpn.game_pk = mk.game_pk AND bpn.batter_id = mk.batter_id
     AND bpn.pitcher_id = mk.pitcher_id AND bpn.reference_date = mk.reference_date
    LEFT JOIN games g ON g.game_pk = mk.game_pk
    LEFT JOIN daily_schedule ds ON ds.game_pk = mk.game_pk
    LEFT JOIN parks pk ON pk.park_id = COALESCE(g.venue_id, ds.venue_id)
    LEFT JOIN projected_lineups pl_any
      ON pl_any.game_pk = mk.game_pk AND pl_any.batter_id = mk.batter_id
    LEFT JOIN projected_lineups pl_home
      ON pl_home.game_pk = mk.game_pk AND pl_home.batter_id = mk.batter_id
     AND pl_home.team_id = ds.home_team_id
    LEFT JOIN players pl_bat ON pl_bat.mlbam_id = mk.batter_id
    LEFT JOIN players pl_pit ON pl_pit.mlbam_id = mk.pitcher_id
    LEFT JOIN LATERAL (
        SELECT wff.*
        FROM weather_forecasts wff
        WHERE wff.park_id = COALESCE(g.venue_id, ds.venue_id)
          AND wff.forecast_for_utc::date IN (
              mk.reference_date,
              mk.reference_date + INTERVAL '1 day'
          )
        ORDER BY wff.fetched_at DESC
        LIMIT 1
    ) wf ON TRUE
    """

    result = session.execute(text(big_sql), {"game_pk": game_pk}).mappings().all()
    return [dict(r) for r in result]


# ---------------------------------------------------------------------------
# Python post-processing (physics, park factors, context derivations)
# ---------------------------------------------------------------------------


def _finalize_row(
    session: Session,
    raw: dict[str, Any],
    *,
    is_historical: bool,
) -> dict[str, Any]:
    """Derive physics / park-factor / context columns from a raw SQL row."""
    out = dict(raw)

    # --- Weather physics --------------------------------------------------
    temp = out.get("wx_temperature_f")
    hum = out.get("wx_humidity_pct")
    press = out.get("wx_pressure_hpa")
    if temp is not None and hum is not None and press is not None:
        out["wx_air_density_relative"] = air_density_relative(float(temp), float(hum), float(press))
    else:
        out["wx_air_density_relative"] = None

    wind_speed = out.get("wx_wind_speed_mph")
    wind_dir = out.get("wx_wind_direction_deg")
    orientation = out.get("park_orientation_deg")
    if wind_speed is not None and wind_dir is not None and orientation is not None:
        lf, cf, rf = wind_carry_components(float(wind_dir), float(wind_speed), float(orientation))
        out["wx_wind_carry_lf"] = lf
        out["wx_wind_carry_cf"] = cf
        out["wx_wind_carry_rf"] = rf
    else:
        out["wx_wind_carry_lf"] = None
        out["wx_wind_carry_cf"] = None
        out["wx_wind_carry_rf"] = None

    # --- Roof gating ------------------------------------------------------
    roof_status = out.get("roof_status")
    park_roof_type = out.get("park_roof_type")
    is_roof_closed = roof_status == "closed" or park_roof_type == "dome"
    out = apply_roof_gating(out, is_roof_closed=is_roof_closed)

    # --- Park factors -----------------------------------------------------
    # Season = the reference year. batter_hand from stand or players.bats.
    ref_date = out["game_date"]
    season = ref_date.year if isinstance(ref_date, date) else int(str(ref_date)[:4])
    park_id = out.get("park_id")
    batter_hand = out.get("batter_stand") or out.get("batter_bats_fallback")
    if park_id is not None and batter_hand in {"L", "R"}:
        out["park_hr_factor_hand"] = park_hr_factor_for(batter_hand, int(park_id), season, session)
        out["park_hr_factor_hand_3yr"] = park_hr_factor_3yr_weighted(
            batter_hand, int(park_id), season, session
        )
    else:
        out["park_hr_factor_hand"] = None
        out["park_hr_factor_hand_3yr"] = None

    # --- Context ----------------------------------------------------------
    batting_order = out.get("ctx_batting_order")
    if batting_order is not None:
        out["ctx_projected_pa"] = PA_BY_BATTING_ORDER.get(int(batting_order))
    else:
        out["ctx_projected_pa"] = None

    # Day/night: historical passes through games.day_night; future derives
    # from game_start_utc.
    raw_dn = out.get("ctx_day_night_raw")
    if raw_dn in {"D", "N"}:
        out["ctx_day_night"] = raw_dn
    else:
        start = out.get("game_start_utc")
        if isinstance(start, datetime):
            out["ctx_day_night"] = day_night_letter(start)
        else:
            out["ctx_day_night"] = None

    # Days rest (batter + pitcher).
    out["ctx_batter_days_rest"] = days_since_last_game(int(out["batter_id"]), ref_date, session)
    out["ctx_pitcher_days_rest"] = days_since_last_game(int(out["pitcher_id"]), ref_date, session)

    # Same-hand — prefer statcast observation, fall back to players table.
    batter_stand = out.get("batter_stand") or out.get("batter_bats_fallback")
    pitcher_throws = out.get("pitcher_throws") or out.get("pitcher_throws_fallback")
    out["ctx_same_hand"] = same_hand(batter_stand, pitcher_throws)

    # TTO penalty from projected PA (or neutral 1.0 when unknown).
    projected_pa = out.get("ctx_projected_pa")
    out["p_tto_penalty"] = tto_penalty_for(float(projected_pa)) if projected_pa else None

    # --- Filter to MatchupFeature columns --------------------------------
    return {k: v for k, v in out.items() if k in _MATCHUP_FEATURE_COLS}


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------


def _upsert_rows(session: Session, rows: list[dict[str, Any]]) -> None:
    """Batch upsert every final row via ON CONFLICT DO UPDATE."""
    if not rows:
        return

    pk_cols = {"game_date", "game_pk", "batter_id", "pitcher_id"}
    non_pk_cols = [c for c in _MATCHUP_FEATURE_COLS if c not in pk_cols and c != "built_at"]

    # Chunk to keep parameter count bounded.
    chunk_size = 200
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        stmt = pg_insert(MatchupFeature).values(chunk)
        update_set = {c: getattr(stmt.excluded, c) for c in non_pk_cols}
        # Refresh built_at on upsert.
        update_set["built_at"] = text("now()")
        stmt = stmt.on_conflict_do_update(
            index_elements=["game_date", "game_pk", "batter_id", "pitcher_id"],
            set_=update_set,
        )
        session.execute(stmt)
