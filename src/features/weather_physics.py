"""Weather physics helpers for Phase 3 feature engineering.

Pure Python — no DB, no network. All inputs and outputs are native
types (float, bool, dict). Consumed by ``src/features/builder.py``.

Formulas per ``phases/phase3/PROMPT.md`` § 3:

* Air density via Magnus (water-vapor partial pressure) + ideal gas law,
  normalized against sea-level-dry standard 1.225 kg/m³.
* Wind carry: cosine component of wind velocity projected onto each
  field-line bearing (LF = park_orientation - 45°, CF = orientation,
  RF = orientation + 45°). Sign convention: positive mph = wind
  blowing toward that field (carry-aiding); negative = suppressing.
* Roof-closed gating: all wx_* columns collapse to climate-neutral
  baselines (72°F / 50% / 1013.25 hPa / density 1.0 / 0 wind).
"""

from __future__ import annotations

import math
from typing import Any

_ROOF_CLOSED_BASELINES: dict[str, Any] = {
    "wx_temperature_f": 72.0,
    "wx_humidity_pct": 50.0,
    "wx_pressure_hpa": 1013.25,
    "wx_air_density_relative": 1.0,
    "wx_wind_speed_mph": 0.0,
    "wx_wind_carry_lf": 0.0,
    "wx_wind_carry_cf": 0.0,
    "wx_wind_carry_rf": 0.0,
}


def air_density_relative(
    temperature_f: float,
    humidity_pct: float,
    pressure_hpa: float,
) -> float:
    """Air density relative to standard sea-level dry at 15°C, 1013.25 hPa (= 1.225 kg/m³).

    Values < 1 → thinner air → more carry. Values > 1 → denser air → more drag.
    """
    t_k = (temperature_f + 459.67) * 5.0 / 9.0
    p_pa = pressure_hpa * 100.0
    # Magnus approximation for saturation vapor pressure (Pa).
    e_sat = 611.2 * math.exp(17.67 * (t_k - 273.15) / (t_k - 29.65))
    e = (humidity_pct / 100.0) * e_sat
    # Ideal gas with humidity correction (dry-air R_d = 287.058 J/(kg·K)).
    rho = (p_pa - 0.378 * e) / (287.058 * t_k)
    return rho / 1.225


def wind_carry_components(
    wind_direction_deg: float,
    wind_speed_mph: float,
    park_orientation_deg: float,
) -> tuple[float, float, float]:
    """(lf, cf, rf) signed mph carry per field per PROMPT § 3.

    ``wind_direction_deg`` is meteorological (direction FROM, cw from N).
    ``park_orientation_deg`` is bearing from home plate to CF, cw from N.
    """
    if wind_speed_mph == 0:
        return 0.0, 0.0, 0.0

    wind_to_deg = (wind_direction_deg + 180.0) % 360.0
    lf_bearing = (park_orientation_deg - 45.0) % 360.0
    cf_bearing = park_orientation_deg % 360.0
    rf_bearing = (park_orientation_deg + 45.0) % 360.0

    def _component(field_bearing_deg: float) -> float:
        return wind_speed_mph * math.cos(math.radians(wind_to_deg - field_bearing_deg))

    return _component(lf_bearing), _component(cf_bearing), _component(rf_bearing)


def apply_roof_gating(
    raw_features: dict[str, Any],
    is_roof_closed: bool,
) -> dict[str, Any]:
    """Return a NEW dict. When ``is_roof_closed`` is True, overwrite every
    wx_* key with the climate-neutral baseline; otherwise pass through.
    ``wx_is_roof_closed`` in the output always matches ``is_roof_closed``.
    """
    out = dict(raw_features)
    if is_roof_closed:
        out.update(_ROOF_CLOSED_BASELINES)
    out["wx_is_roof_closed"] = is_roof_closed
    return out
