"""The two-stage cash-flow model.

Most of these guard against a large, confident, wrong number: the ways a
discounted cash flow goes wrong are all quiet, and all produce output that
looks fine.
"""

from __future__ import annotations

import pytest

from hedge_fund.valuation.dcf import DCFError, Drivers, sensitivity, simulate, value


def _d(**over) -> Drivers:
    args = {
        "revenue": 1_000.0,
        "revenue_growth": 0.05,
        "target_operating_margin": 0.20,
        "sales_to_capital": 2.0,
        "cost_of_capital": 0.09,
        "tax_rate": 0.25,
        "terminal_growth": 0.02,
        "shares": 100.0,
    }
    args.update(over)
    return Drivers(**args)


# ------------------------------------------------------------------
# The refusals
# ------------------------------------------------------------------


def test_terminal_growth_at_or_above_the_cost_of_capital_is_refused():
    # The terminal value would be negative or infinite; both arrive as a number.
    with pytest.raises(DCFError, match="negative or infinite"):
        value(_d(terminal_growth=0.09))


def test_terminal_growth_above_the_riskfree_rate_is_refused():
    with pytest.raises(DCFError, match="outgrowing the economy"):
        value(_d(terminal_growth=0.06), riskfree=0.045)


@pytest.mark.parametrize(
    ("over", "match"),
    [
        ({"revenue": 0}, "revenue must be positive"),
        ({"shares": 0}, "share count"),
        ({"cost_of_capital": 0}, "cost of capital"),
        ({"tax_rate": 1.0}, "tax rate"),
        ({"sales_to_capital": 0}, "sales-to-capital"),
        ({"failure_probability": 1.5}, "failure probability"),
        ({"years": 0}, "at least one year"),
    ],
)
def test_inputs_that_would_produce_a_plausible_wrong_number_are_refused(over, match):
    with pytest.raises(DCFError, match=match):
        value(_d(**over))


# ------------------------------------------------------------------
# The mechanics
# ------------------------------------------------------------------


def test_growth_consumes_capital_and_that_lowers_the_value():
    # Leaving reinvestment out is what makes naive models generous.
    cheap_growth = value(_d(sales_to_capital=10.0)).value_per_share
    dear_growth = value(_d(sales_to_capital=1.0)).value_per_share
    assert cheap_growth > dear_growth


def test_the_margin_walks_from_today_to_the_target():
    v = value(_d(current_operating_margin=0.10, target_operating_margin=0.20))
    first, last = v.years[0]["operating_margin"], v.years[-1]["operating_margin"]
    assert 0.10 < first < 0.20
    assert last == pytest.approx(0.20)


def test_net_debt_comes_off_the_equity_value():
    with_debt = value(_d(net_debt=500.0)).value_per_share
    without = value(_d(net_debt=0.0)).value_per_share
    assert without - with_debt == pytest.approx(5.0)  # 500 / 100 shares


def test_a_chance_of_failure_reduces_the_value():
    safe = value(_d(failure_probability=0.0)).value_per_share
    risky = value(_d(failure_probability=0.3)).value_per_share
    assert risky < safe


def test_recovery_in_failure_softens_the_hit():
    none = value(_d(failure_probability=0.3, failure_recovery=0.0)).value_per_share
    some = value(_d(failure_probability=0.3, failure_recovery=0.5)).value_per_share
    assert some > none


def test_the_terminal_value_share_is_reported_because_it_is_usually_most_of_it():
    v = value(_d())
    assert 0.0 < v.terminal_share_of_value < 1.0
    assert len(v.years) == 10


def test_a_higher_cost_of_capital_lowers_the_value():
    assert (
        value(_d(cost_of_capital=0.12)).value_per_share
        < value(_d(cost_of_capital=0.08)).value_per_share
    )


# ------------------------------------------------------------------
# The distribution
# ------------------------------------------------------------------


def test_the_same_inputs_give_the_same_distribution():
    # A value that moves between two runs of the same inputs cannot be
    # compared with last month's.
    a = simulate(_d(), runs=500, seed=7)
    b = simulate(_d(), runs=500, seed=7)
    assert a["percentiles"] == b["percentiles"]
    assert a["seed"] == 7


def test_a_different_seed_gives_a_different_draw():
    a = simulate(_d(), runs=500, seed=7)
    b = simulate(_d(), runs=500, seed=8)
    assert a["percentiles"] != b["percentiles"]


def test_the_percentiles_are_ordered():
    p = simulate(_d(), runs=800)["percentiles"]
    assert p["p5"] <= p["p10"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p90"] <= p["p95"]


def test_the_price_turns_the_range_into_a_probability():
    s = simulate(_d(), price=5.0, runs=800)
    assert 0.0 <= s["probability_value_above_price"] <= 1.0
    assert "median_upside_pct" in s


def test_without_a_price_there_is_no_probability_invented():
    assert "probability_value_above_price" not in simulate(_d(), runs=500)


def test_too_few_runs_is_refused_as_decoration():
    with pytest.raises(DCFError, match="decoration"):
        simulate(_d(), runs=50)


def test_impossible_draws_are_counted_not_clamped():
    s = simulate(_d(), runs=500)
    assert s["rejected"] >= 0
    assert s["runs"] + s["rejected"] >= 500


def test_the_independence_simplification_is_stated_rather_than_hidden():
    assert "independently" in simulate(_d(), runs=200)["independence_note"]


# ------------------------------------------------------------------
# The sensitivity grid
# ------------------------------------------------------------------


def test_the_grid_covers_both_axes():
    g = sensitivity(_d())["grid"]
    assert len(g) == 5
    assert len(g[0]["values"]) == 5


def test_an_impossible_cell_records_why_instead_of_failing_the_table():
    # A grid that throws on one cell tells you nothing about the other 24.
    g = sensitivity(_d(cost_of_capital=0.03), terminal_growth_steps=(0.0, 0.02))["grid"]
    cells = [c for row in g for c in row["values"]]
    assert any("refused" in c for c in cells)
    assert any("value_per_share" in c for c in cells)
