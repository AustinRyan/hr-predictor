"""Phase 1 data quality audit.

Writes a markdown report covering row counts, null rates, FK integrity,
venue coverage, date gaps, suspicious extremes, and three hardcoded spot
checks. The audit does not modify any data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from src.core.db import get_engine

_log = logging.getLogger(__name__)

_NULLABLE_COLS: tuple[str, ...] = (
    "pitch_type",
    "release_speed",
    "release_spin_rate",
    "effective_speed",
    "launch_speed",
    "launch_angle",
    "hit_distance_sc",
    "hc_x",
    "hc_y",
    "events",
    "description",
    "balls",
    "strikes",
    "outs_when_up",
    "inning",
    "inning_topbot",
    "stand",
    "p_throws",
    "estimated_woba_using_speedangle",
    "estimated_ba_using_speedangle",
    "woba_value",
    "woba_denom",
    "launch_speed_angle",
    "zone",
    "plate_x",
    "plate_z",
    "home_team",
    "away_team",
    "bat_speed",
    "swing_length",
)


@dataclass(slots=True)
class AuditSection:
    heading: str
    body: str


def run_audit(engine: Engine | None = None, out_dir: Path | None = None) -> Path:
    """Generate the Phase 1 audit report and return its path."""
    engine = engine or get_engine()
    out_dir = out_dir or Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    sections = [
        _row_counts_section(engine),
        _null_rates_section(engine),
        _fk_integrity_section(engine),
        _venue_coverage_section(engine),
        _date_gaps_section(engine),
        _suspicious_values_section(engine),
        _spot_checks_section(engine),
    ]

    today = date.today().strftime("%Y%m%d")
    report_path = out_dir / f"phase1_audit_{today}.md"
    body_lines = ["# Phase 1 — Data Quality Audit", f"Generated: {date.today().isoformat()}", ""]
    for sec in sections:
        body_lines.append(f"## {sec.heading}")
        body_lines.append("")
        body_lines.append(sec.body.rstrip())
        body_lines.append("")
    report_path.write_text("\n".join(body_lines))
    _log.info("audit report written", extra={"path": str(report_path)})
    return report_path


# ----------------------------------------------------------------------
# Sections
# ----------------------------------------------------------------------


def _row_counts_section(engine: Engine) -> AuditSection:
    with engine.connect() as c:
        rows = c.execute(text("""
                SELECT EXTRACT(year FROM game_date)::int AS season,
                       COUNT(*) AS pitches,
                       COUNT(DISTINCT game_pk) AS games
                FROM statcast_pitches
                GROUP BY 1
                ORDER BY 1
                """)).all()
        totals = c.execute(
            text(
                "SELECT COUNT(*), COUNT(DISTINCT game_pk), COUNT(DISTINCT batter), COUNT(DISTINCT pitcher) FROM statcast_pitches"
            )
        ).one()
    body = "| season | pitches | games |\n|---|---:|---:|\n"
    for r in rows:
        body += f"| {r.season} | {r.pitches:,} | {r.games:,} |\n"
    body += f"\n**Totals:** {totals[0]:,} pitches, {totals[1]:,} games, {totals[2]:,} distinct batters, {totals[3]:,} distinct pitchers"
    return AuditSection("Row counts per season", body)


def _null_rates_section(engine: Engine) -> AuditSection:
    lines = ["| season | " + " | ".join(_NULLABLE_COLS) + " |"]
    lines.append("|---|" + "|".join(["---:"] * len(_NULLABLE_COLS)) + "|")
    with engine.connect() as c:
        seasons = [
            r[0]
            for r in c.execute(
                text(
                    "SELECT DISTINCT EXTRACT(year FROM game_date)::int FROM statcast_pitches ORDER BY 1"
                )
            ).all()
        ]
        for season in seasons:
            total = c.execute(
                text("SELECT COUNT(*) FROM statcast_pitches WHERE EXTRACT(year FROM game_date)=:y"),
                {"y": season},
            ).scalar_one()
            if not total:
                continue
            parts = [str(season)]
            for col in _NULLABLE_COLS:
                nulls = c.execute(
                    text(
                        f"SELECT COUNT(*) FROM statcast_pitches WHERE EXTRACT(year FROM game_date)=:y AND {col} IS NULL"
                    ),
                    {"y": season},
                ).scalar_one()
                pct = (nulls / total) * 100 if total else 0.0
                parts.append(f"{pct:.1f}%")
            lines.append("| " + " | ".join(parts) + " |")
    return AuditSection("Null rates by column, per season (%)", "\n".join(lines))


def _fk_integrity_section(engine: Engine) -> AuditSection:
    with engine.connect() as c:
        orphan_batters = c.execute(text("""
                SELECT COUNT(DISTINCT batter) FROM statcast_pitches p
                LEFT JOIN players pl ON pl.mlbam_id = p.batter
                WHERE pl.mlbam_id IS NULL
                """)).scalar_one()
        orphan_pitchers = c.execute(text("""
                SELECT COUNT(DISTINCT pitcher) FROM statcast_pitches p
                LEFT JOIN players pl ON pl.mlbam_id = p.pitcher
                WHERE pl.mlbam_id IS NULL
                """)).scalar_one()
        orphan_games = c.execute(text("""
                SELECT COUNT(DISTINCT p.game_pk) FROM statcast_pitches p
                LEFT JOIN games g ON g.game_pk = p.game_pk
                WHERE g.game_pk IS NULL
                """)).scalar_one()
    body = (
        f"- Batters in pitches missing from players: **{orphan_batters}**\n"
        f"- Pitchers in pitches missing from players: **{orphan_pitchers}**\n"
        f"- game_pks in pitches missing from games: **{orphan_games}**"
    )
    return AuditSection("FK integrity", body)


def _venue_coverage_section(engine: Engine) -> AuditSection:
    with engine.connect() as c:
        missing = c.execute(text("""
                SELECT DISTINCT g.venue_id FROM games g
                LEFT JOIN parks p ON p.park_id = g.venue_id
                WHERE g.venue_id IS NOT NULL AND p.park_id IS NULL
                """)).scalars().all()
        total_parks = c.execute(text("SELECT COUNT(*) FROM parks")).scalar_one()
        parks_with_full_attrs = c.execute(text("""
                SELECT COUNT(*) FROM parks
                WHERE orientation_deg IS NOT NULL
                  AND elevation_ft IS NOT NULL
                  AND roof_type IS NOT NULL
                """)).scalar_one()
    body = (
        f"- Parks rows: **{total_parks}** (of which {parks_with_full_attrs} have full orientation/elevation/roof)\n"
        f"- Games referencing an unknown venue_id: **{len(missing)}**"
    )
    if missing:
        body += "\n  - Missing venue_ids: " + ", ".join(str(v) for v in missing)
    return AuditSection("Venue coverage", body)


def _date_gaps_section(engine: Engine) -> AuditSection:
    # Report calendar-day gaps inside each season's observed date range,
    # minus a handful of predictable off-days (All-Star break, etc).
    with engine.connect() as c:
        by_season = c.execute(text("""
                SELECT EXTRACT(year FROM game_date)::int AS season,
                       MIN(game_date) AS first_date,
                       MAX(game_date) AS last_date,
                       COUNT(DISTINCT game_date) AS days_with_pitches
                FROM statcast_pitches
                GROUP BY 1
                ORDER BY 1
                """)).all()
    lines = [
        "| season | first | last | days with pitches | calendar days | gap |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in by_season:
        cal_days = (row.last_date - row.first_date).days + 1
        gap = cal_days - row.days_with_pitches
        lines.append(
            f"| {row.season} | {row.first_date} | {row.last_date} | {row.days_with_pitches} | {cal_days} | {gap} |"
        )
    lines.append(
        "\nGap is calendar days minus days-with-pitches. Off days (All-Star break, early-week breaks, World Series travel days) are expected to create small gaps."
    )
    return AuditSection("Date coverage", "\n".join(lines))


def _suspicious_values_section(engine: Engine) -> AuditSection:
    with engine.connect() as c:
        high_ev = c.execute(
            text("SELECT COUNT(*) FROM statcast_pitches WHERE launch_speed > 125")
        ).scalar_one()
        crazy_angle = c.execute(
            text("SELECT COUNT(*) FROM statcast_pitches WHERE ABS(launch_angle) > 90")
        ).scalar_one()
        hr_with_no_launch = c.execute(
            text(
                "SELECT COUNT(*) FROM statcast_pitches WHERE events='home_run' AND launch_speed IS NULL"
            )
        ).scalar_one()
    body = (
        f"- Rows with launch_speed > 125 mph: **{high_ev}**\n"
        f"- Rows with |launch_angle| > 90°: **{crazy_angle}**\n"
        f"- HR rows with NULL launch_speed (inside-the-park / bugs): **{hr_with_no_launch}**"
    )
    return AuditSection("Suspicious values", body)


def _spot_checks_section(engine: Engine) -> AuditSection:
    """Three hardcoded correctness checks. IDs are looked up, not hardcoded."""
    results: list[str] = []
    with engine.connect() as c:
        judge_id = _lookup_player_id(c, "Aaron", "Judge")
        if judge_id is None:
            results.append("- **Aaron Judge**: id lookup failed")
        else:
            row = c.execute(
                text("""
                    SELECT COUNT(*) AS n, MIN(launch_speed) AS min_ls, MAX(launch_speed) AS max_ls
                    FROM statcast_pitches
                    WHERE events='home_run' AND batter=:b AND game_date='2022-10-04'
                    """),
                {"b": judge_id},
            ).one()
            ok = row.n == 1 and row.min_ls and 99 <= row.min_ls <= 101
            results.append(
                f"- **Judge 62nd HR** (2022-10-04, mlbam={judge_id}): {row.n} HR row(s), launch_speed={row.min_ls} → {'PASS' if ok else 'INVESTIGATE'}"
            )

        ohtani_id = _lookup_player_id(c, "Shohei", "Ohtani")
        if ohtani_id is None:
            results.append("- **Shohei Ohtani**: id lookup failed")
        else:
            n = c.execute(
                text("""
                    SELECT COUNT(*) FROM statcast_pitches
                    WHERE events='home_run' AND batter=:b AND EXTRACT(year FROM game_date)=2024
                    """),
                {"b": ohtani_id},
            ).scalar_one()
            results.append(
                f"- **Ohtani 2024 HRs** (mlbam={ohtani_id}): {n} → {'PASS' if n >= 50 else 'INVESTIGATE (expected ≥50)'}"
            )

        coors_id = c.execute(
            text("SELECT park_id FROM parks WHERE name ILIKE 'Coors Field'")
        ).scalar()
        if coors_id is None:
            results.append("- **Coors Field**: id lookup failed")
        else:
            n = c.execute(
                text("""
                    SELECT COUNT(*) FROM statcast_pitches p
                    JOIN games g ON g.game_pk = p.game_pk
                    WHERE g.venue_id=:v AND p.events='home_run' AND g.season=2023
                    """),
                {"v": coors_id},
            ).scalar_one()
            results.append(
                f"- **Coors Field 2023 HRs** (park_id={coors_id}): {n} → {'PASS' if n >= 180 else 'INVESTIGATE (expected ≥180)'}"
            )

    return AuditSection("Spot checks", "\n".join(results))


def _lookup_player_id(conn: Connection, first: str, last: str) -> int | None:
    # Prefer our DB enrichment; fall back to pybaseball if absent.
    row = conn.execute(
        text("""
            SELECT mlbam_id FROM players
            WHERE LOWER(first_name)=:f AND LOWER(last_name)=:l
            ORDER BY mlbam_id DESC LIMIT 1
            """),
        {"f": first.lower(), "l": last.lower()},
    ).scalar()
    if row is not None:
        return int(row)
    try:
        import pybaseball

        df = pybaseball.playerid_lookup(last.lower(), first.lower())
        if df is not None and not df.empty:
            val = df.iloc[0].get("key_mlbam")
            if val is not None:
                return int(val)
    except Exception:  # pragma: no cover - network/lookup dependent
        pass
    return None


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def main() -> int:  # pragma: no cover
    from src.core.logging_config import configure_logging

    configure_logging()
    path = run_audit()
    print(path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
