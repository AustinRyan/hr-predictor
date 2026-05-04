#!/usr/bin/env bash
# Run the daily HR-predictor pipeline locally and write fresh predictions
# into the shared Neon database. The deployed Vercel frontend reads from
# the same DB, so clicking around on the live site will show the new
# picks within a few minutes (next page load).
#
# Prerequisites:
#   - DATABASE_URL in your shell env (or in .env at the repo root) points
#     at the Neon instance (postgresql://...sslmode=require).
#   - Docker must NOT be running Postgres on 5432 at the Neon URL — this
#     script uses whatever DATABASE_URL resolves to.
#
# Usage:
#   ./scripts/refresh-picks.sh           # runs for today's UTC date
#   ./scripts/refresh-picks.sh 2026-04-25  # explicit date override
#
# Typical runtime: ~2-5 minutes (mostly weather + statcast API calls).

set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${DATABASE_URL:-}" && -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL not set. Export it or put it in .env." >&2
  exit 1
fi

TARGET_DATE="${1:-$(date -u +%Y-%m-%d)}"
echo "→ refreshing predictions for ${TARGET_DATE}"
echo "→ database: $(printf '%s' "$DATABASE_URL" | sed -E 's|(://[^:]+:)[^@]+(@)|\1***\2|')"

echo
echo "[1/4] ingesting schedule + lineups + weather + statcast"
uv run python -c "
from datetime import date
from src.ingestion.daily_runner import run_daily
r = run_daily(target_date=date.fromisoformat('${TARGET_DATE}'))
print(f'  games={r.games} weather_rows={r.weather_rows} statcast_pitches={r.statcast_pitches} failures={r.failures}')
"

echo
echo "[2/4] filling proxy lineups for any teams missing today's lineup"
uv run python -c "
from datetime import date
from sqlalchemy import text
from src.core.db import get_engine
engine = get_engine()
sql = text('''
    WITH today_teams AS (
        SELECT game_pk, home_team_id AS team_id FROM daily_schedule WHERE game_date = :d
        UNION ALL
        SELECT game_pk, away_team_id AS team_id FROM daily_schedule WHERE game_date = :d
    ),
    teams_needing_proxy AS (
        SELECT tt.game_pk, tt.team_id
        FROM today_teams tt
        LEFT JOIN projected_lineups pl
          ON pl.game_pk = tt.game_pk AND pl.team_id = tt.team_id
        WHERE pl.id IS NULL
        GROUP BY tt.game_pk, tt.team_id
    ),
    recent_src AS (
        SELECT DISTINCT ON (pl.team_id)
            pl.team_id, pl.game_pk AS src_game_pk
        FROM projected_lineups pl
        JOIN daily_schedule ds ON ds.game_pk = pl.game_pk
        WHERE ds.game_date < :d
          AND pl.team_id IN (SELECT team_id FROM teams_needing_proxy)
        ORDER BY pl.team_id, ds.game_date DESC, pl.fetched_at DESC
    )
    INSERT INTO projected_lineups (game_pk, team_id, batter_id, batting_order, is_confirmed)
    SELECT tn.game_pk, tn.team_id, src.batter_id, src.batting_order, FALSE
    FROM teams_needing_proxy tn
    JOIN recent_src rs ON rs.team_id = tn.team_id
    JOIN projected_lineups src
        ON src.game_pk = rs.src_game_pk AND src.team_id = rs.team_id
''')
with engine.begin() as c:
    n = c.execute(sql, {'d': date.fromisoformat('${TARGET_DATE}')}).rowcount
print(f'  proxy lineup rows inserted: {n}')
"

echo
echo "[3/4] building matchup_features + running inference"
uv run python -c "
from src.features.builder import build_features_for_today
from src.models.inference import generate_predictions_for_date
from datetime import date
fr = build_features_for_today()
print(f'  matchup_features rows: {fr}')
rows = generate_predictions_for_date(date.fromisoformat('${TARGET_DATE}'))
print(f'  predictions written: {rows}')
"

echo
echo "[4/4] fetching sportsbook odds"
if [[ -z "${PROP_LINE_API_KEY:-}" ]]; then
  echo "  skipped: PROP_LINE_API_KEY not set"
else
  uv run python -c "
from datetime import date
import re

from src.ingestion.prop_line_odds import persist_mlb_batter_hr_odds

def _redact(value: str) -> str:
    return re.sub(r'([?&]apiKey=)[^&\s]+', r'\1***', value, flags=re.IGNORECASE)

try:
    r = persist_mlb_batter_hr_odds(date.fromisoformat('${TARGET_DATE}'))
except Exception as exc:
    msg = _redact(str(exc) or exc.__class__.__name__)
    print(f'  odds skipped: {msg}')
    print('  predictions are still current; rerun later to refresh sportsbook edge')
else:
    print(
        f'  odds_rows={r.rows_written} events={r.events_matched}/{r.events_seen} '
        f'unmatched_players={len(r.unmatched_players)} failures={r.failures}'
    )
"
fi

echo
echo "✓ refresh complete for ${TARGET_DATE}"
echo "  reload the deployed site to see fresh picks and real odds edge"
