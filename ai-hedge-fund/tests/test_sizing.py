"""Sizing a candidate against an existing book."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hedge_fund.decisions.sizing import HIGH_CORRELATION, assess_addition


class FakeDS:
    """Serves correlated or independent series so the maths can be checked."""

    def __init__(self, mapping: dict[str, float] | None = None, seed: int = 0):
        self.mapping = mapping or {}
        self.rng = np.random.default_rng(seed)
        self.base = self.rng.normal(0.0005, 0.012, 500)

    def get_price_history(self, ticker, days=365, end_date=None):
        idx = pd.date_range("2024-01-01", periods=500, freq="B")
        rho = self.mapping.get(ticker.upper(), 0.0)
        noise = self.rng.normal(0.0005, 0.012, 500)
        rets = rho * self.base + math_sqrt(1 - rho**2) * noise
        return pd.DataFrame({"close": 100 * np.exp(np.cumsum(rets))}, index=idx)


def math_sqrt(x: float) -> float:
    return float(np.sqrt(max(x, 0.0)))


def _book(*weights: tuple[str, float]) -> dict:
    total = sum(w for _, w in weights)
    return {
        "total_value": total,
        "cash": 50_000.0,
        "currency": "USD",
        "holdings_count": len(weights),
        "holdings": [
            {"ticker": t, "market_value": v, "weight_pct": round(v / total * 100, 2)}
            for t, v in weights
        ],
    }


def test_weight_is_measured_against_the_whole_book():
    a = assess_addition(
        ticker="NEW",
        proposed_value=10_000,
        portfolio=_book(("AAA", 90_000)),
        data_service=FakeDS(),
    )
    assert a.proposed_weight_pct == pytest.approx(11.11, abs=0.1)


def test_adding_to_an_existing_holding_accumulates():
    a = assess_addition(
        ticker="AAA",
        proposed_value=10_000,
        portfolio=_book(("AAA", 40_000), ("BBB", 60_000)),
        data_service=FakeDS(),
    )
    assert a.existing_weight_pct == pytest.approx(40.0, abs=0.1)
    assert a.proposed_weight_pct == pytest.approx(50.0, abs=0.1)


def test_exceeding_cash_is_flagged_not_silently_negative():
    a = assess_addition(
        ticker="NEW",
        proposed_value=80_000,
        portfolio=_book(("AAA", 100_000)),
        data_service=FakeDS(),
    )
    assert a.funded_by_cash is False
    assert any("exceeds available cash" in f for f in a.flags)


def test_a_dominant_position_is_flagged():
    a = assess_addition(
        ticker="NEW",
        proposed_value=50_000,
        portfolio=_book(("AAA", 50_000)),
        data_service=FakeDS(),
    )
    assert any("of the book" in f for f in a.flags)


def test_a_correlated_addition_is_called_out():
    """Buying something that moves with the book is more exposure, not more names."""
    ds = FakeDS({"AAA": 0.95, "NEW": 0.95})
    a = assess_addition(
        ticker="NEW",
        proposed_value=10_000,
        portfolio=_book(("AAA", 90_000)),
        data_service=ds,
    )
    assert a.correlation_to_book is not None and a.correlation_to_book > HIGH_CORRELATION
    assert any("moves with the existing book" in f for f in a.flags)


def test_an_uncorrelated_addition_can_lower_portfolio_volatility():
    ds = FakeDS({"AAA": 0.95, "NEW": 0.0})
    a = assess_addition(
        ticker="NEW",
        proposed_value=25_000,
        portfolio=_book(("AAA", 75_000)),
        data_service=ds,
    )
    assert a.correlation_to_book is not None and abs(a.correlation_to_book) < 0.3
    assert a.diversifying is True
    assert a.portfolio_volatility_after_pct < a.portfolio_volatility_before_pct


def test_concentration_is_reported_before_and_after():
    a = assess_addition(
        ticker="NEW",
        proposed_value=10_000,
        portfolio=_book(("A", 40_000), ("B", 30_000), ("C", 20_000), ("D", 10_000)),
        data_service=FakeDS(),
    )
    assert a.concentration_top3_before_pct is not None
    assert a.concentration_top3_after_pct is not None


def test_an_empty_book_is_handled():
    a = assess_addition(
        ticker="NEW",
        proposed_value=10_000,
        portfolio={"total_value": 0.0, "cash": 20_000.0, "holdings": [], "currency": "USD"},
        data_service=FakeDS(),
    )
    assert a.proposed_weight_pct == pytest.approx(100.0, abs=0.1)
    assert any("nothing to compare" in note for note in a.notes)


def test_missing_price_history_degrades_rather_than_raises():
    class Dead:
        def get_price_history(self, *a, **k):
            return pd.DataFrame()

    a = assess_addition(
        ticker="NEW",
        proposed_value=10_000,
        portfolio=_book(("AAA", 90_000)),
        data_service=Dead(),
    )
    assert a.correlation_to_book is None
    assert a.proposed_weight_pct is not None


def test_a_degenerate_total_cannot_produce_an_absurd_weight():
    """Defensive: a reported total smaller than the position must not read as 1000%.

    `total_value` includes cash, so this state should not occur — but a weight in
    the thousands of percent would look like a data error rather than the sizing
    bug it actually is.
    """
    a = assess_addition(
        ticker="NEW",
        proposed_value=10_000,
        portfolio={"total_value": 0.0, "cash": 0.0, "holdings": [], "currency": "USD"},
        data_service=FakeDS(),
    )
    assert a.proposed_weight_pct <= 100.0
