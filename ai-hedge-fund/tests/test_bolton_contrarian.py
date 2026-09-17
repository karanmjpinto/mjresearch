"""The Bolton contrarian screen.

The screen's job is narrow and it matters that it stays narrow: find companies
that are cheap, out of favour and solvent enough to wait. It must NOT imply it
has found a buy, because Bolton's own framework says cheap-without-a-catalyst
is a value trap, and the catalyst is the one section no data feed carries.
"""

from __future__ import annotations

import pytest

from hedge_fund.api.routes.screeners import SCREEN_FIELDS
from hedge_fund.screeners import cache
from hedge_fund.screeners.bolton_contrarian import (
    BoltonSnapshot,
    _band,
    score_bolton_contrarian,
)


def _cheap_and_hated(**over) -> BoltonSnapshot:
    """A textbook candidate: cheap on everything, near its low, able to pay."""
    base = dict(
        ticker="TEST",
        market_cap=2_000_000_000,
        price_current=12.0,
        price_52w_high=30.0,
        price_52w_low=10.0,
        trailing_pe=7.0,
        price_to_book=0.5,
        ev_to_ebitda=5.0,
        free_cash_flow_ttm=300_000_000,
        operating_cash_flow_ttm=400_000_000,
        net_income_ttm=250_000_000,
        ebit_ttm=400_000_000,
        interest_expense_ttm=50_000_000,
        debt_to_equity=0.8,
        short_percent_float=0.18,
        analyst_count=4,
        held_percent_institutions=0.45,
        insider_buys_12m=3,
        insider_sells_12m=0,
        return_6m_pct=-30.0,
        return_1m_pct=2.0,
    )
    base.update(over)
    return BoltonSnapshot(**base)


def test_the_textbook_candidate_passes_and_scores_well():
    r = score_bolton_contrarian(_cheap_and_hated())
    assert r.passed, r.failures
    assert r.composite is not None and r.composite >= 70
    assert r.tier == "strong"
    assert len(r.cheap_on) == 4


def test_a_loved_expensive_stock_fails_on_both_counts():
    r = score_bolton_contrarian(
        _cheap_and_hated(
            trailing_pe=38.0,
            price_to_book=45.0,
            ev_to_ebitda=26.0,
            free_cash_flow_ttm=1_000_000,
            price_current=29.0,
        )
    )
    assert not r.passed
    assert "not_cheap_on_any_measure" in r.failures
    assert "not_out_of_favour" in r.failures


def test_cheap_but_still_popular_is_rejected():
    """Cheapness alone is not the screen. Bolton wants the market to have left.

    A stock at its 52-week high on a low multiple is a different thesis — it is
    a growth-at-a-reasonable-price idea, not a contrarian one — and letting it
    through would fill the list with names nobody has given up on.
    """
    r = score_bolton_contrarian(_cheap_and_hated(price_current=28.0))
    assert not r.passed
    assert r.failures == ["not_out_of_favour"]
    # But it is still scored, so it can be inspected rather than vanishing.
    assert r.composite is not None and r.composite > 0


def test_it_never_claims_to_have_checked_the_catalyst():
    """The load-bearing honesty of the whole screen.

    If this ever reports True, the screen is claiming to have done the one
    piece of Bolton's process it cannot do, and every name in the list becomes
    a buy recommendation it has no basis for.
    """
    for snap in (_cheap_and_hated(), _cheap_and_hated(trailing_pe=99.0)):
        assert score_bolton_contrarian(snap).catalyst_checked is False


def test_leverage_ceiling_and_interest_floor_reject_the_fragile():
    over = score_bolton_contrarian(_cheap_and_hated(debt_to_equity=3.0))
    assert "leverage_above_ceiling" in over.failures

    thin = score_bolton_contrarian(
        _cheap_and_hated(ebit_ttm=40_000_000, interest_expense_ttm=50_000_000)
    )
    assert "interest_cover_below_floor" in thin.failures


def test_a_debt_free_company_is_not_punished_for_having_no_interest_cover():
    """No interest expense means nothing to cover, which is the strong case.

    Treating an undefined ratio as a failure would reject exactly the
    balance sheets his checklist prefers.
    """
    r = score_bolton_contrarian(_cheap_and_hated(interest_expense_ttm=None, debt_to_equity=0.0))
    assert r.passed, r.failures
    assert r.balance_sheet_score >= 15.0


def test_cash_burn_is_disqualifying():
    r = score_bolton_contrarian(_cheap_and_hated(operating_cash_flow_ttm=-10_000_000))
    assert "no_operating_cash_flow" in r.failures


def test_missing_multiples_do_not_penalise_the_valuation_score():
    """A company with no P/E must not score worse than one with a bad P/E.

    The screen rescales by how many measures were available. Summing absent
    ones as zero would rank a loss-making turnaround — Bolton's core hunting
    ground — below an expensive stock that reports everything.
    """
    full = score_bolton_contrarian(_cheap_and_hated())
    partial = score_bolton_contrarian(_cheap_and_hated(trailing_pe=None, ev_to_ebitda=None))
    assert partial.valuation_score == pytest.approx(full.valuation_score, abs=6.0)


def test_insider_selling_scores_below_insider_buying():
    buying = score_bolton_contrarian(_cheap_and_hated(insider_buys_12m=4, insider_sells_12m=0))
    quiet = score_bolton_contrarian(_cheap_and_hated(insider_buys_12m=0, insider_sells_12m=0))
    selling = score_bolton_contrarian(_cheap_and_hated(insider_buys_12m=0, insider_sells_12m=6))
    assert buying.insider_score > quiet.insider_score > selling.insider_score


def test_an_unfetchable_name_is_an_error_not_a_failure():
    r = score_bolton_contrarian(BoltonSnapshot(ticker="X", error="rate limited"))
    assert r.error == "rate limited"
    assert r.passed is False
    assert r.composite is None, "a name that could not be read must not get a score"


def test_band_clamps_and_runs_in_both_directions():
    assert _band(5.0, 5.0, 20.0, 10.0) == 10.0
    assert _band(20.0, 5.0, 20.0, 10.0) == 0.0
    assert _band(100.0, 5.0, 20.0, 10.0) == 0.0  # clamped, not negative
    assert _band(None, 5.0, 20.0, 10.0) == 0.0
    # Higher-is-better reads the same helper with best above worst.
    assert _band(9.0, 9.0, 3.0, 7.0) == 7.0
    assert _band(3.0, 9.0, 3.0, 7.0) == 0.0


def test_every_cached_screen_has_a_field_mapping():
    """Adding a screen without a row here sorts it on a key it does not have.

    That exact defect shipped once: the compounder fell through to the `else`
    branch, was sorted on a missing key, and rendered an unranked list that
    looked ranked.
    """
    missing = sorted(set(cache.SCREENS) - set(SCREEN_FIELDS))
    assert not missing, f"screens with no field mapping: {missing}"
