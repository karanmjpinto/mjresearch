"""EBITDA growth, the factor that was silently never computed.

The Yartseva screen penalises a company whose assets grow faster than its
EBITDA — capital going in without earnings coming out. The penalty needs an
EBITDA growth rate, that rate needed the prior year's TTM, and the prior TTM is
summed from quarters four through eight of the quarterly income statement.

yfinance returns four to seven quarters. `_sum_q` refuses a short window — a
three-quarter "TTM" would understate the base and inflate the growth rate — so
it returned None every single time, for every company. The penalty was
therefore always zero: a designed check that had never once fired, on scores
presented as though it had.

These tests pin both halves: the sum still refuses a short window, and the
annual fallback supplies the number instead.
"""

from __future__ import annotations

import pandas as pd

from hedge_fund.screeners.yartseva import _annual_yoy, _sum_q


def _frame(row: str, values: list[float]) -> pd.DataFrame:
    cols = pd.date_range("2026-06-30", periods=len(values), freq="-1QE")
    return pd.DataFrame([values], index=[row], columns=cols)


def test_short_window_is_still_refused():
    """The original guard stays. Seven quarters cannot make two TTMs."""
    seven = _frame("EBITDA", [10.0] * 7)
    assert _sum_q(seven, "EBITDA", 0, 4) == 40.0
    assert _sum_q(seven, "EBITDA", 4, 8) is None


def test_annual_fallback_computes_the_growth_rate():
    # Most recent fiscal year first, which is how yfinance orders columns.
    df = _frame("EBITDA", [120.0, 100.0, 90.0])
    assert _annual_yoy(df, "EBITDA") == 20.0


def test_annual_fallback_handles_a_negative_prior_year():
    """A loss-making prior year must not flip the sign of the growth rate.

    Dividing by a negative base would report a recovery from -50 to +50 as
    -200% growth — a company that doubled its earnings scored as collapsing.
    """
    df = _frame("EBITDA", [50.0, -50.0])
    assert _annual_yoy(df, "EBITDA") == 200.0


def test_one_year_of_history_is_not_a_growth_rate():
    assert _annual_yoy(_frame("EBITDA", [100.0]), "EBITDA") is None


def test_missing_and_empty_inputs_return_none():
    assert _annual_yoy(None, "EBITDA") is None
    assert _annual_yoy(pd.DataFrame(), "EBITDA") is None
    assert _annual_yoy(_frame("Total Revenue", [1.0, 2.0]), "EBITDA") is None


def test_zero_prior_year_is_not_infinite_growth():
    assert _annual_yoy(_frame("EBITDA", [100.0, 0.0]), "EBITDA") is None


def test_nans_are_dropped_not_treated_as_zero():
    """A missing year must be skipped, not read as zero EBITDA.

    Filling it with zero would manufacture either infinite growth or a
    catastrophic decline out of an absent filing.
    """
    df = _frame("EBITDA", [120.0, float("nan"), 100.0])
    assert _annual_yoy(df, "EBITDA") == 20.0
