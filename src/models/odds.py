"""Sportsbook odds math used to compare model probabilities to market prices."""

from __future__ import annotations


def _validate_probability(probability: float, *, name: str) -> float:
    value = float(probability)
    if not 0.0 < value < 1.0:
        raise ValueError(f"{name} must be between 0 and 1, exclusive")
    return value


def american_to_implied_probability(american_odds: int) -> float:
    """Return break-even implied probability for American odds."""
    odds = int(american_odds)
    if odds == 0:
        raise ValueError("American odds cannot be 0")
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def probability_to_fair_american(probability: float) -> int:
    """Convert a fair probability to nearest whole-number American odds."""
    p = _validate_probability(probability, name="probability")
    if p >= 0.5:
        return round(-100.0 * p / (1.0 - p))
    return round(100.0 * (1.0 - p) / p)


def edge_probability(*, model_probability: float, market_probability: float) -> float:
    """Return model probability minus market-implied probability."""
    model_p = _validate_probability(model_probability, name="model_probability")
    market_p = _validate_probability(market_probability, name="market_probability")
    return model_p - market_p


def expected_value_per_unit(*, model_probability: float, american_odds: int) -> float:
    """Return expected profit/loss in stake units for a one-unit bet."""
    p = _validate_probability(model_probability, name="model_probability")
    odds = int(american_odds)
    if odds == 0:
        raise ValueError("American odds cannot be 0")
    profit_if_win = odds / 100.0 if odds > 0 else 100.0 / abs(odds)
    return p * profit_if_win - (1.0 - p)
