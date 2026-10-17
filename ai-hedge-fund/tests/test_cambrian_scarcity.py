"""The Cambrian scarcity screen: the arithmetic it does, and the things it refuses."""

from __future__ import annotations

import pytest

from hedge_fund.screeners import cambrian_scarcity as cs


def _snap(**kw) -> cs.ScarcitySnapshot:
    base = dict(
        ticker="TEST",
        segment="wafers",
        quote_currency="JPY",
        financial_currency="JPY",
        industry="Semiconductor Equipment & Materials",
        market_cap=200.0,
        revenue_ntm=100.0,
        revenue_multiple=2.0,
        ppe_to_revenue=0.5,
        torque=5.0,
        idle_gap_pp=15.0,
        demand_growth=0.25,
        net_debt_to_ebitda=0.0,
    )
    base.update(kw)
    return cs.ScarcitySnapshot(**base)


def test_their_own_illustration_gives_their_own_answer():
    """55 fixed, 30 variable, 15 profit: +10% volume is +47% profit."""
    # Gross profit 70 with no depreciation in cost of goods; EBIT 15.
    dol, why = cs.torque_of(70.0, 0.0, 15.0)
    assert why is None
    assert dol * 0.10 == pytest.approx(0.467, abs=0.001)


def test_a_loss_maker_has_undefined_torque_not_infinite_torque():
    assert cs.torque_of(40.0, 10.0, -5.0) == (None, "operating_loss")
    r = cs.evaluate(_snap(torque=None, torque_unmeasured_reason="operating_loss"))
    assert r.passed
    assert r.scores["torque"] == cs.WEIGHTS["torque"] / 2


def test_a_perfect_name_scores_100_and_the_weights_sum_to_100():
    assert sum(cs.WEIGHTS.values()) == 100
    assert cs.evaluate(_snap()).composite == 100


def test_calendarisation_blends_the_two_fiscal_years():
    year = 365.25 * 86_400
    # A quarter of the current fiscal year left to run.
    ntm = cs.calendarise(100.0, 200.0, last_fy_end=0.0, now=0.75 * year)
    assert ntm == pytest.approx(0.25 * 100 + 0.75 * 200)
    assert cs.calendarise(None, 200.0, 0.0, 0.0) is None


def test_fabless_and_software_fail_the_physical_filter_by_name():
    for seg in ("fabless", "software"):
        r = cs.evaluate(_snap(segment=seg))
        assert not r.passed
        assert "not_physical_supply_chain" in r.failures


def test_a_semiconductor_label_without_plant_is_refused_as_fabless():
    """Off the curated list, the label lets every designer in; plant does not."""
    r = cs.evaluate(_snap(segment=None, industry="Semiconductors", ppe_to_revenue=0.06))
    assert r.failures == ["no_factories"]


def test_plant_held_in_a_joint_venture_is_exempt_by_name_only():
    assert cs.evaluate(_snap(ticker="SNDK", ppe_to_revenue=0.03)).passed
    assert not cs.evaluate(_snap(ticker="OTHER", ppe_to_revenue=0.03)).passed


def test_an_unconvertible_currency_refuses_the_multiple_rather_than_guessing():
    r = cs.evaluate(
        _snap(quote_currency="HKD", financial_currency="USD", fx_rate=None, revenue_multiple=None)
    )
    assert "currency_not_convertible" in r.failures


def test_memory_rows_carry_the_price_taker_tension():
    assert cs.evaluate(_snap(segment="memory")).price_taker_tension
    assert not cs.evaluate(_snap(segment="wafers")).price_taker_tension


def test_every_curated_segment_is_known():
    known = set(cs.PHYSICAL_SEGMENTS) | {"fabless", "software"}
    assert {seg for seg, _ in cs.SEGMENT_BY_TICKER.values()} <= known
