"""The Kiyohara handbook screen.

Two things are being protected here. The first is that the screen prices the
*second* year, because that is the single thing he says distinguishes his page
of the Handbook from everyone else's reading of it. The second is the pair of
holes: which of his four P/E ceilings applies, and who the founder's family
is. Both are judgments the feed cannot make, and a screen that quietly filled
them in would be handing back a buy list with his name on it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from hedge_fund.api.routes.screeners import SCREEN_FIELDS
from hedge_fund.screeners import cache
from hedge_fund.screeners.kiyohara_handbook import (
    IGNORED_BY_DESIGN,
    KiyoharaSnapshot,
    _share_history,
    score_kiyohara_handbook,
)


def _handbook_candidate(**over) -> KiyoharaSnapshot:
    """A textbook name off his page: cheap on next year, thick equity, net cash."""
    base = dict(
        ticker="9999.T",
        name="Test Seisakusho",
        currency="JPY",
        sector="Industrials",
        industry="Specialty Industrial Machinery",
        market_cap=50_000_000_000,
        price_current=1_000.0,
        eps_trailing=90.0,
        eps_fy1=100.0,
        eps_fy2=120.0,
        fy2_analyst_count=4,
        total_assets=100_000_000_000,
        stockholders_equity=60_000_000_000,
        cash_and_st_investments=25_000_000_000,
        total_debt=5_000_000_000,
        shares_latest=100_000_000,
        shares_oldest=102_000_000,
        share_history_years=4,
        equity_issued_recently=False,
        held_percent_insiders=0.35,
    )
    base.update(over)
    return KiyoharaSnapshot(**base)


def test_the_textbook_candidate_passes_and_scores_well():
    r = score_kiyohara_handbook(_handbook_candidate())
    assert r.passed, r.failures
    assert r.composite is not None and r.composite >= 70
    assert r.tier == "strong"
    assert r.pe_second_year == pytest.approx(8.33, abs=0.05)
    # Under three of his four ceilings. Not the fourth: 8.3x is more than he
    # would pay for a subcontractor living off a handful of customers, which
    # is the point of reporting the ceilings rather than a single verdict.
    assert r.tiers_cleared == [
        "global niche leader",
        "many credible customers",
        "small/mid real estate",
    ]


def test_the_multiple_is_taken_on_the_second_year_not_the_first():
    """His one distinctive instruction, and the easiest to get wrong.

    A company whose current year looks cheap but whose next year collapses is
    the exact name this screen exists to refuse, and a first-year multiple
    would wave it through at 10x.
    """
    collapsing = score_kiyohara_handbook(_handbook_candidate(eps_fy1=100.0, eps_fy2=20.0))
    assert collapsing.pe_first_year == pytest.approx(10.0)
    assert collapsing.pe_second_year == pytest.approx(50.0)
    assert not collapsing.passed
    assert "above_every_pe_tier" in collapsing.failures


def test_a_name_with_no_second_year_forecast_is_unjudgeable_not_expensive():
    r = score_kiyohara_handbook(_handbook_candidate(eps_fy1=None, eps_fy2=None))
    assert "no_second_year_forecast" in r.failures
    assert "above_every_pe_tier" not in r.failures, (
        "a missing forecast must not be reported as a failed valuation test"
    )


def test_real_estate_is_held_to_his_own_tighter_ceiling():
    """The one tier a sector code actually settles, so it is enforced.

    Small and mid-cap Japanese real estate was his bread and butter and he
    would not pay past 10x for it. The same multiple elsewhere is fine,
    because the ceiling depends on the business.
    """
    at_twelve = dict(eps_fy2=1_000.0 / 12)
    property_co = score_kiyohara_handbook(_handbook_candidate(sector="Real Estate", **at_twelve))
    assert not property_co.passed
    assert "above_real_estate_tier" in property_co.failures
    assert property_co.pe_ceiling_applied == 10.0

    machinery = score_kiyohara_handbook(_handbook_candidate(**at_twelve))
    assert machinery.passed, machinery.failures
    assert machinery.pe_ceiling_applied == 20.0


def test_a_thin_equity_ratio_is_disqualifying():
    """ "Enough of a cushion to avoid any kind of dilution" is a hard test.

    The whole point of the equity ratio on his page is that the next downturn
    must not end in a share issue, so a name that would need one does not
    belong on the list at any multiple.
    """
    r = score_kiyohara_handbook(
        _handbook_candidate(stockholders_equity=15_000_000_000)  # 15% of assets
    )
    assert "equity_ratio_below_floor" in r.failures
    assert r.equity_ratio == pytest.approx(0.15)


def test_it_never_claims_to_have_checked_the_business_type_or_the_founder():
    """The two load-bearing admissions.

    `business_type_checked` reporting True would mean the screen had decided
    which of his four ceilings applies — a market-share judgment no feed
    carries. `founder_stake_checked` would mean it had found the founder's
    family in a register it has never seen. Either one turns a candidate list
    into a recommendation.
    """
    for snap in (
        _handbook_candidate(),
        _handbook_candidate(eps_fy2=1.0),
        _handbook_candidate(sector="Real Estate"),
    ):
        r = score_kiyohara_handbook(snap)
        assert r.business_type_checked is False
        assert r.founder_stake_checked is False


def test_every_ceiling_the_name_clears_is_reported_rather_than_one_chosen():
    r = score_kiyohara_handbook(_handbook_candidate(eps_fy2=1_000.0 / 17))  # 17x
    assert r.tiers_cleared == ["global niche leader"]
    assert r.passed, r.failures


def test_issuing_equity_scores_nothing_and_a_buyback_scores_well():
    """Not a veto — he says it is noted, not disqualifying — but it costs."""
    issued = score_kiyohara_handbook(_handbook_candidate(equity_issued_recently=True))
    quiet = score_kiyohara_handbook(_handbook_candidate())
    buying_back = score_kiyohara_handbook(
        _handbook_candidate(shares_latest=90_000_000, shares_oldest=100_000_000)
    )
    assert issued.capital_discipline_score == 0.0
    assert buying_back.capital_discipline_score > quiet.capital_discipline_score
    assert issued.passed, "issuance is a mark against, not a hard filter"


def test_net_cash_is_scored_but_debt_is_not_punished_twice():
    rich = score_kiyohara_handbook(_handbook_candidate())
    geared = score_kiyohara_handbook(_handbook_candidate(total_debt=40_000_000_000))
    assert rich.net_cash_score > geared.net_cash_score
    assert geared.net_cash_score == 0.0, "negative net cash scores zero, never negative"


def test_an_unknown_currency_is_refused_rather_than_converted():
    """A size floor in the wrong currency is invisible and wrong both ways.

    Applying the yen floor to a dollar quote rejects everything; applying the
    dollar floor to a won quote admits every micro-cap. So the screen says it
    cannot judge the size instead of inventing a rate.
    """
    r = score_kiyohara_handbook(_handbook_candidate(currency="KRW"))
    assert "size_floor_unknown_currency" in r.failures


def test_a_split_is_not_mistaken_for_an_equity_issue():
    """The error this section must not make.

    Balance-sheet share counts are as reported, so a two-for-one split — which
    Japanese mid caps do routinely and which dilutes nobody — doubles the
    count. Read naively that is "the company issued half of itself", which
    inverts the only question this part of his checklist asks.
    """
    index = pd.to_datetime(["2026-03-31", "2025-03-31", "2024-03-31", "2023-03-31"])
    bs = pd.DataFrame(
        [[200.0, 200.0, 100.0, 100.0]],
        index=["Ordinary Shares Number"],
        columns=index,
    )
    splits = pd.Series([2.0], index=pd.to_datetime(["2024-06-01"]))

    latest, oldest, years = _share_history(bs, splits)
    assert (latest, oldest, years) == (200.0, 200.0, 4)

    # Without the split on file the same numbers are a genuine doubling.
    assert _share_history(bs)[1] == 100.0


def test_the_screen_reads_none_of_what_he_says_to_ignore():
    """ "Everything else you can ignore. Dividend, price chart etc."

    The omissions are his instruction, so they are asserted rather than
    assumed: a later edit that adds a dividend yield or a 52-week range to
    this screen has changed whose method it is.
    """
    r = score_kiyohara_handbook(_handbook_candidate())
    fields = set(r.to_dict()) | set(r.snapshot)
    banned = ("dividend", "yield", "chart", "52w", "fifty_two", "recommend", "rating", "return_")
    for field_name in fields:
        assert not any(b in field_name.lower() for b in banned), (
            f"{field_name!r} is something Kiyohara explicitly ignores: {IGNORED_BY_DESIGN}"
        )


def test_an_unfetchable_name_is_an_error_not_a_failure():
    r = score_kiyohara_handbook(KiyoharaSnapshot(ticker="X.T", error="rate limited"))
    assert r.error == "rate limited"
    assert r.passed is False
    assert r.composite is None, "a name that could not be read must not get a score"


def test_the_screen_is_wired_to_the_cache_and_the_results_route():
    assert "kiyohara-handbook" in cache.SCREENS
    assert "kiyohara-handbook" in SCREEN_FIELDS
