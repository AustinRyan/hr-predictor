"""CLI tests for src.features.builder."""

from __future__ import annotations

from datetime import date

from src.features import builder


def test_builder_cli_runs_closed_date_range(monkeypatch, capsys) -> None:
    calls: list[tuple[date, date]] = []

    def fake_build_features_for_historical(start_date: date, end_date: date) -> int:
        calls.append((start_date, end_date))
        return 123

    monkeypatch.setattr(
        builder,
        "build_features_for_historical",
        fake_build_features_for_historical,
    )

    exit_code = builder._main(["--start", "2026-04-01", "--end", "2026-04-03"])

    assert exit_code == 0
    assert calls == [(date(2026, 4, 1), date(2026, 4, 3))]
    assert "matchup_features rows: 123" in capsys.readouterr().out


def test_builder_cli_runs_bullpen_only_closed_date_range(monkeypatch, capsys) -> None:
    calls: list[tuple[date, date]] = []

    def fake_backfill_team_bullpen_features(start_date: date, end_date: date) -> int:
        calls.append((start_date, end_date))
        return 456

    monkeypatch.setattr(
        builder,
        "backfill_team_bullpen_features",
        fake_backfill_team_bullpen_features,
    )

    exit_code = builder._main(
        ["--start", "2026-04-01", "--end", "2026-04-03", "--team-bullpen-only"]
    )

    assert exit_code == 0
    assert calls == [(date(2026, 4, 1), date(2026, 4, 3))]
    assert "matchup_features rows: 456" in capsys.readouterr().out


def test_builder_cli_rejects_partial_range(capsys) -> None:
    exit_code = builder._main(["--start", "2026-04-01"])

    assert exit_code == 2
    assert "--start and --end must be provided together" in capsys.readouterr().err
