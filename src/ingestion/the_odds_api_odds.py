"""Persist The Odds API MLB batter home-run odds into Postgres."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.engine import Engine

from src.ingestion.prop_line_odds import (
    OddsIngestionReport,
    PropLineOddsClient,
    persist_mlb_batter_hr_odds_from_client,
)
from src.ingestion.the_odds_api_client import TheOddsApiClient


def persist_mlb_batter_hr_odds_from_the_odds_api(
    target_date: date,
    *,
    engine: Engine | None = None,
    client: PropLineOddsClient | None = None,
    fetched_at: datetime | None = None,
) -> OddsIngestionReport:
    """Fetch and persist The Odds API MLB batter home-run odds for a slate date."""
    return persist_mlb_batter_hr_odds_from_client(
        target_date,
        engine=engine,
        client=client or TheOddsApiClient(),
        provider="the_odds_api",
        provider_label="The Odds API",
        fetched_at=fetched_at,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch The Odds API MLB batter HR odds")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    report = persist_mlb_batter_hr_odds_from_the_odds_api(args.date)
    print(
        "odds rows="
        f"{report.rows_written} events={report.events_matched}/{report.events_seen} "
        f"unmatched_players={len(report.unmatched_players)} failures={report.failures}",
        flush=True,
    )


if __name__ == "__main__":
    main()
