"""Unit tests for Phase 3 weather physics helpers.

All expected values are taken from phases/phase3/PROMPT.md § 3 and
§ "Acceptance checklist — Physics sanity checks". If the numbers here
disagree with the PROMPT, the PROMPT wins — update the tests.
"""

from __future__ import annotations

import math

import pytest
from src.features.weather_physics import (
    air_density_relative,
    apply_roof_gating,
    wind_carry_components,
)

# ---------- air_density_relative ----------


def test_air_density_hot_day() -> None:
    """95°F, 60% humidity, sea-level pressure → thinner air."""
    rho = air_density_relative(95.0, 60.0, 1013.0)
    assert rho == pytest.approx(0.923, abs=0.01)


def test_air_density_cold_day() -> None:
    """40°F, 40% humidity, sea-level pressure → denser air."""
    rho = air_density_relative(40.0, 40.0, 1013.0)
    assert rho == pytest.approx(1.036, abs=0.01)


def test_air_density_standard_conditions() -> None:
    """15°C (59°F), dry-ish (20%), 1013.25 hPa → near 1.0."""
    rho = air_density_relative(59.0, 20.0, 1013.25)
    assert rho == pytest.approx(1.0, abs=0.01)


# ---------- wind_carry_components ----------


def test_wind_from_west_at_north_oriented_park() -> None:
    """Wind FROM 270° (west), 15 mph, park orientation 0° (CF=north).
    Wind blows TO east (90°). LF at 315°, CF at 0°, RF at 45°.

    Components (from PROMPT acceptance checklist):
      lf ≈ -10.6 (suppresses LF — wind is blowing away from LF direction)
      cf ≈ 0 (perpendicular)
      rf ≈ +10.6 (aids RF — wind blows toward RF)
    """
    lf, cf, rf = wind_carry_components(
        wind_direction_deg=270.0,
        wind_speed_mph=15.0,
        park_orientation_deg=0.0,
    )
    assert lf == pytest.approx(-10.6, abs=0.5)
    assert cf == pytest.approx(0.0, abs=0.5)
    assert rf == pytest.approx(10.6, abs=0.5)


def test_wind_directly_out_to_cf() -> None:
    """Wind blowing toward CF (wind FROM 180° = from south, blowing north) at 10 mph,
    park orientation 0° (CF=north).
      cf ≈ +10
      lf, rf ≈ +7.07 (cos 45° component)
    """
    lf, cf, rf = wind_carry_components(
        wind_direction_deg=180.0,
        wind_speed_mph=10.0,
        park_orientation_deg=0.0,
    )
    assert cf == pytest.approx(10.0, abs=0.1)
    assert lf == pytest.approx(10.0 * math.cos(math.radians(45)), abs=0.1)
    assert rf == pytest.approx(10.0 * math.cos(math.radians(45)), abs=0.1)


def test_wind_speed_zero_returns_zeros() -> None:
    lf, cf, rf = wind_carry_components(
        wind_direction_deg=123.0,
        wind_speed_mph=0.0,
        park_orientation_deg=42.0,
    )
    assert lf == 0.0
    assert cf == 0.0
    assert rf == 0.0


# ---------- apply_roof_gating ----------


def test_apply_roof_gating_closed_overwrites_weather_columns() -> None:
    """Closed roof → climate-neutral baselines per PROMPT § 3."""
    raw = {
        "wx_temperature_f": 95.0,
        "wx_humidity_pct": 30.0,
        "wx_pressure_hpa": 997.0,
        "wx_air_density_relative": 0.95,
        "wx_wind_speed_mph": 12.0,
        "wx_wind_carry_lf": -8.0,
        "wx_wind_carry_cf": 3.0,
        "wx_wind_carry_rf": 5.0,
        "wx_is_roof_closed": False,  # the input says open, gating will flip
    }
    gated = apply_roof_gating(raw, is_roof_closed=True)
    assert gated["wx_temperature_f"] == 72.0
    assert gated["wx_humidity_pct"] == 50.0
    assert gated["wx_pressure_hpa"] == 1013.25
    assert gated["wx_air_density_relative"] == 1.0
    assert gated["wx_wind_speed_mph"] == 0.0
    assert gated["wx_wind_carry_lf"] == 0.0
    assert gated["wx_wind_carry_cf"] == 0.0
    assert gated["wx_wind_carry_rf"] == 0.0
    assert gated["wx_is_roof_closed"] is True


def test_apply_roof_gating_open_passthrough() -> None:
    """Open roof → input values passed through, only wx_is_roof_closed = False."""
    raw = {
        "wx_temperature_f": 78.0,
        "wx_humidity_pct": 55.0,
        "wx_pressure_hpa": 1010.0,
        "wx_air_density_relative": 0.98,
        "wx_wind_speed_mph": 8.0,
        "wx_wind_carry_lf": 2.0,
        "wx_wind_carry_cf": -3.0,
        "wx_wind_carry_rf": 5.0,
        "wx_is_roof_closed": True,  # will be overwritten to False
    }
    gated = apply_roof_gating(raw, is_roof_closed=False)
    assert gated["wx_temperature_f"] == 78.0
    assert gated["wx_humidity_pct"] == 55.0
    assert gated["wx_pressure_hpa"] == 1010.0
    assert gated["wx_air_density_relative"] == 0.98
    assert gated["wx_wind_speed_mph"] == 8.0
    assert gated["wx_wind_carry_lf"] == 2.0
    assert gated["wx_wind_carry_cf"] == -3.0
    assert gated["wx_wind_carry_rf"] == 5.0
    assert gated["wx_is_roof_closed"] is False


def test_apply_roof_gating_does_not_mutate_input() -> None:
    """Must return a new dict; caller's input is unchanged."""
    raw = {
        "wx_temperature_f": 88.0,
        "wx_humidity_pct": 40.0,
        "wx_pressure_hpa": 1005.0,
        "wx_air_density_relative": 0.95,
        "wx_wind_speed_mph": 6.0,
        "wx_wind_carry_lf": 1.0,
        "wx_wind_carry_cf": 2.0,
        "wx_wind_carry_rf": 3.0,
        "wx_is_roof_closed": False,
    }
    raw_copy = dict(raw)
    apply_roof_gating(raw, is_roof_closed=True)
    assert raw == raw_copy, "apply_roof_gating must not mutate input"
