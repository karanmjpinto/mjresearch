"""Running the valuation backwards.

The property that matters is not "returns a number" — it is that a returned
number is *the* number, and that an unreachable price returns nothing rather
than the edge of the search bracket. A clamped answer looks exactly like a real
one on a screen, which is the failure these tests exist to prevent.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from hedge_fund.valuation.dcf import Drivers, value
from hedge_fund.valuation.implied import (
    BRACKETS,
    implied_driver,
    implied_set,
)

RF = 0.0497


def base() -> Drivers:
    """Apple-shaped, so the numbers below are recognisable rather than toy."""
    return Drivers(
        revenue=416_161_000_000.0,
        revenue_growth=0.06,
        target_operating_margin=0.3478,
        current_operating_margin=0.3478,
        sales_to_capital=2.414,
        cost_of_capital=0.09809,
        tax_rate=0.25,
        terminal_growth=0.025,
        net_debt=98_657_000_000.0,
        shares=14_594_180_236.1,
        years=10,
    )


def test_the_solved_driver_actually_reproduces_the_price() -> None:
    """The one test that matters: put the answer back in and the model agrees."""
    d = base()
    price = 331.34
    g = implied_driver(d, "revenue_growth", price, riskfree=RF)
    assert g is not None
    back = value(replace(d, revenue_growth=g), riskfree=RF).value_per_share
    assert abs(back - price) < 0.01


def test_a_price_the_model_already_agrees_with_implies_the_current_driver() -> None:
    """Solve for the price the base case already produces: you get back where you started."""
    d = base()
    here = value(d, riskfree=RF).value_per_share
    g = implied_driver(d, "revenue_growth", here, riskfree=RF)
    assert g is not None
    assert g == pytest.approx(d.revenue_growth, abs=1e-3)


def test_a_higher_price_implies_more_growth() -> None:
    d = base()
    low = implied_driver(d, "revenue_growth", 120.0, riskfree=RF)
    high = implied_driver(d, "revenue_growth", 240.0, riskfree=RF)
    assert low is not None and high is not None
    assert high > low


def test_an_unreachable_price_returns_nothing_not_the_bracket_edge() -> None:
    """The failure this module exists to avoid.

    No revenue growth inside any defensible range values Apple at $40,000 a
    share. Returning 100% — the top of the bracket — would render as a real
    answer and be read as one.
    """
    d = base()
    out = implied_driver(d, "revenue_growth", 40_000.0, riskfree=RF)
    assert out is None or out < BRACKETS["revenue_growth"][1]
    if out is not None:
        back = value(replace(d, revenue_growth=out), riskfree=RF).value_per_share
        assert abs(back - 40_000.0) < 0.01, "a returned figure must reproduce the price"


def test_a_driver_that_cannot_reach_the_price_alone_says_so() -> None:
    """Apple at $331 is not reachable by margin alone, even at 90%."""
    d = base()
    assert implied_driver(d, "target_operating_margin", 331.34, riskfree=RF) is None


def test_a_zero_or_negative_price_is_not_solved() -> None:
    d = base()
    assert implied_driver(d, "revenue_growth", 0.0, riskfree=RF) is None
    assert implied_driver(d, "revenue_growth", -5.0, riskfree=RF) is None


def test_an_unknown_driver_is_a_programming_error_not_a_none() -> None:
    with pytest.raises(ValueError, match="no search bracket"):
        implied_driver(base(), "vibes", 100.0, riskfree=RF)


def test_the_solve_does_not_mutate_the_callers_drivers() -> None:
    """Every driver is solved against the same object; one mutation poisons the rest."""
    d = base()
    before = (d.revenue_growth, d.target_operating_margin, d.sales_to_capital)
    implied_set(d, 331.34, riskfree=RF)
    assert (d.revenue_growth, d.target_operating_margin, d.sales_to_capital) == before


def test_the_set_covers_every_bracketed_driver_and_says_what_it_is() -> None:
    out = implied_set(base(), 331.34, riskfree=RF)
    assert set(out["drivers"]) == set(BRACKETS)
    assert out["price"] == 331.34
    # The caveat is load-bearing: solved one at a time, these do not hold
    # together as a set, and quoting them as one would be wrong.
    assert "not a set that holds together" in out["note"]


def test_apple_at_todays_price_implies_growth_nobody_would_type() -> None:
    """The finding that makes this worth building.

    Pinned loosely: the point is that the implied figure is far above anything
    a reader would put in the box unprompted, not that it is 23.4% forever.
    """
    g = implied_driver(base(), "revenue_growth", 331.34, riskfree=RF)
    assert g is not None
    assert g > 0.15, "if this drops below 15% the anchor has stopped being surprising"
