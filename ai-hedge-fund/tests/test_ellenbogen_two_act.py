"""The Ellenbogen two-act screen.

Three things are being protected, and they are the three ways this screen
could quietly stop being his framework.

The first is that the scored trait is the *slope* of return on invested
capital, not its level — "they got better as they got bigger" — and that the
slope is refused rather than reported whenever it would be an artefact: a
business that did not actually get bigger, or a capital base shrinking under a
buyback, which lifts the ratio with no operating improvement at all. A screen
that took that number at face value would make its signature test its least
reliable one.

The second is the profitable core. His own re-underwriting after rates reset
turned on it, and the line he repeats to founders is that ignoring
profitability is not the Amazon story. A loss-maker must fail, however fast it
is growing.

The third is the pair of holes. Whether there is a second act, and whether this
is a founder on their second act, are the judgments the framework is made of.
Every row has to say it has not checked them, and the drawdown must never be
scored — scoring it turns a quality screen into a falling-knife screen wearing
his name.
"""

from __future__ import annotations

import pytest

from hedge_fund.api.routes.screeners import SCREEN_FIELDS
from hedge_fund.screeners import cache, criteria
from hedge_fund.screeners.ellenbogen_two_act import (
    MIN_IC_TO_REVENUE_TO_JUDGE_ROIC,
    MIN_REV_GROWTH_TO_JUDGE_SLOPE,
    STRUCTURAL_DRAWDOWN,
    TRANSITION_DRAWDOWN,
    UNCHECKABLE_BY_DESIGN,
    EllenbogenSnapshot,
    _roic_series,
    score_ellenbogen_two_act,
)


def _act1_candidate(**over) -> EllenbogenSnapshot:
    """A company with the signature: growing, profitable, returns rising.

    Revenue roughly doubles across four years, EBIT grows faster than the
    capital behind it, so the return on that capital climbs while the business
    gets bigger — which is the whole test.
    """
    base = dict(
        ticker="TEST",
        name="Test Compounder Inc",
        currency="USD",
        sector="Technology",
        industry="Software - Application",
        market_cap=3_000_000_000,
        price_current=100.0,
        revenue_annual=[500.0, 625.0, 780.0, 975.0],
        ebit_annual=[50.0, 75.0, 110.0, 160.0],
        gross_profit_annual=[300.0, 390.0, 500.0, 650.0],
        invested_capital_annual=[400.0, 460.0, 530.0, 610.0],
        revenue_ttm=975.0,
        ebit_ttm=160.0,
        gross_profit_ttm=650.0,
        free_cash_flow_ttm=120.0,
        net_income_ttm=110.0,
        tax_rate=0.25,
        reinvestment_rate=0.45,
        shares_latest=100_000_000,
        shares_oldest=100_500_000,
        share_history_years=5,
        held_percent_insiders=0.18,
        price_high_5y=110.0,
    )
    base.update(over)
    return EllenbogenSnapshot(**base)


def test_the_signature_candidate_passes_and_scores_well():
    r = score_ellenbogen_two_act(_act1_candidate())
    assert r.passed, r.failures
    assert r.composite is not None and r.composite >= 70
    assert r.tier == "strong"
    # Returns rose while the business grew: that is the trait being bought.
    assert r.roic_slope_measured is True
    assert r.roic_change_pp is not None and r.roic_change_pp > 0


def test_the_slope_is_the_scored_trait_not_the_level():
    """A high flat return is a good business. His study found the other thing.

    Both companies here earn the same return on capital today. One has held it
    while trebling; the other climbed to it from a low base while growing by
    the same amount. The second must score higher, or this screen is just the
    compounder screen with a different name on it.
    """
    flat = score_ellenbogen_two_act(
        _act1_candidate(
            ebit_annual=[82.0, 102.0, 128.0, 160.0],
            invested_capital_annual=[310.0, 390.0, 490.0, 610.0],
        )
    )
    rising = score_ellenbogen_two_act(_act1_candidate())
    assert flat.roic == pytest.approx(rising.roic, rel=0.02)
    assert rising.returns_on_capital_score > flat.returns_on_capital_score


def test_a_flat_business_cannot_claim_the_slope():
    """ "Better as it got bigger" needs the bigger.

    Margin recovery on a business that did not grow is a different story and a
    much commoner one, so the slope is reported unmeasured and scored neutral
    rather than counted as the trait.
    """
    r = score_ellenbogen_two_act(
        _act1_candidate(
            revenue_annual=[950.0, 955.0, 965.0, 975.0],
            revenue_ttm=975.0,
        )
    )
    assert r.roic_slope_measured is False
    assert r.roic_slope_unmeasured_reason == "business_did_not_get_bigger"
    assert r.revenue_growth_over_window is not None
    assert r.revenue_growth_over_window < MIN_REV_GROWTH_TO_JUDGE_SLOPE
    # And it fails outright on growth, which is the other half of Act 1.
    assert "revenue_cagr_below_floor" in r.failures


def test_a_shrinking_capital_base_does_not_count_as_rising_returns():
    """The buyback artefact, which is the one this screen had to get right.

    Retiring stock reduces equity, equity sits inside invested capital, so the
    ratio climbs with no operating improvement whatsoever. Treated as a
    measurement it would score a company full marks on the trait his research
    found, for having bought back shares.
    """
    r = score_ellenbogen_two_act(
        _act1_candidate(
            ebit_annual=[120.0, 130.0, 145.0, 160.0],
            invested_capital_annual=[700.0, 640.0, 580.0, 500.0],
        )
    )
    assert r.roic_change_pp is not None and r.roic_change_pp > 0
    assert r.roic_slope_measured is False
    assert r.roic_slope_unmeasured_reason == "capital_base_shrank"


def test_a_financed_away_capital_base_is_not_a_530_percent_return():
    """Found on a real name, not in review: Medpace prints 530% here.

    Years of buybacks took invested capital to 3% of revenue, and NOPAT over
    almost nothing is a denominator artefact rather than a return on capital.
    The level leg would have handed it full marks for having financed the
    capital away. It is not failed either — the business genuinely earns a lot
    on very little — it is reported as unrankable and scored neutral.
    """
    r = score_ellenbogen_two_act(
        _act1_candidate(
            invested_capital_annual=[547.0, 456.0, 282.0, 28.0],
        )
    )
    assert r.roic is not None and r.roic > 1.0
    assert r.roic_level_measured is False
    assert r.roic_level_unmeasured_reason == "capital_base_financed_away"
    assert r.invested_capital_to_revenue is not None
    assert r.invested_capital_to_revenue < MIN_IC_TO_REVENUE_TO_JUDGE_ROIC
    # Neither rewarded nor refused.
    assert "roic_below_floor" not in r.failures
    normal = score_ellenbogen_two_act(_act1_candidate())
    assert r.returns_on_capital_score < normal.returns_on_capital_score


def test_the_unmeasured_slope_is_neutral_not_nil():
    """Six of twelve, with the reason on the row.

    Zero would rank an unmeasurable company below a measured bad one, which
    makes "not checked" indistinguishable from "checked and poor" — the exact
    confusion the rest of this codebase exists to refuse.
    """
    flat = score_ellenbogen_two_act(_act1_candidate(revenue_annual=[950.0, 955.0, 965.0, 975.0]))
    declining = score_ellenbogen_two_act(
        _act1_candidate(
            ebit_annual=[110.0, 100.0, 95.0, 90.0],
            ebit_ttm=90.0,
        )
    )
    assert flat.roic_slope_measured is False
    assert declining.roic_slope_measured is True
    assert declining.roic_change_pp is not None and declining.roic_change_pp < 0


def test_a_loss_making_grower_fails_however_fast_it_grows():
    """ "That's interesting, because that's not the Amazon story."

    The imposter filter. Growth funded by nothing is what fell 70% when money
    stopped being free, and it is what his 2022 re-underwriting removed.
    """
    r = score_ellenbogen_two_act(
        _act1_candidate(
            revenue_annual=[200.0, 400.0, 700.0, 1_200.0],
            ebit_annual=[-40.0, -70.0, -110.0, -150.0],
            revenue_ttm=1_200.0,
            ebit_ttm=-150.0,
        )
    )
    assert not r.passed
    assert "core_not_profitable" in r.failures


def test_growth_that_has_already_stopped_fails():
    """A flattering five-year CAGR on a business that stalled last year."""
    r = score_ellenbogen_two_act(
        _act1_candidate(
            revenue_annual=[500.0, 700.0, 960.0, 975.0],
            revenue_ttm=975.0,
        )
    )
    assert not r.passed
    assert "growth_has_stalled" in r.failures
    # The CAGR itself is fine, which is the point of having both tests.
    assert r.revenue_cagr is not None and r.revenue_cagr > 0.12


def test_dilution_is_refused_even_though_his_own_book_held_it():
    """A house rule applied to a borrowed framework, and stated as one."""
    r = score_ellenbogen_two_act(
        _act1_candidate(shares_latest=130_000_000, shares_oldest=100_000_000)
    )
    assert not r.passed
    assert "dilutes_the_holder" in r.failures


def test_a_missing_gross_margin_is_not_a_failure():
    """Services compounders book labour in cost of revenue, or omit the line.

    FirstService and Colliers are two of his own, so failing a name for a
    field the provider did not return would remove the companies the framework
    was partly built on.
    """
    r = score_ellenbogen_two_act(_act1_candidate(gross_profit_annual=[], gross_profit_ttm=None))
    assert r.passed, r.failures
    assert r.gross_margin is None
    assert "gross_margin_below_floor" not in r.failures


def test_the_size_band_refuses_an_unknown_currency():
    """Refused rather than converted at a rate invented in the screen."""
    r = score_ellenbogen_two_act(_act1_candidate(currency="KRW"))
    assert not r.passed
    assert "cap_band_unknown_currency" in r.failures


def test_a_megacap_is_above_the_ceiling():
    r = score_ellenbogen_two_act(_act1_candidate(market_cap=900_000_000_000))
    assert not r.passed
    assert "above_cap_ceiling" in r.failures


def test_the_standing_exclusions_apply_here_too():
    for sector, industry, pid in (
        ("Consumer Defensive", "Tobacco", "excluded_vice"),
        ("Industrials", "Aerospace & Defense", "excluded_defence"),
        ("Energy", "Oil & Gas E&P", "excluded_fossil_extraction"),
    ):
        r = score_ellenbogen_two_act(_act1_candidate(sector=sector, industry=industry))
        assert not r.passed
        assert pid in r.failures, (sector, industry, r.failures)


def test_the_drawdown_is_reported_and_never_scored():
    """His most distinctive claim, and the one easiest to misuse.

    Two identical businesses, one down 55% from its five-year high. The
    drawdown must change the flag and the reported figure, and must not change
    the score by a single point — otherwise this is a cheapness screen with his
    name on it.
    """
    intact = score_ellenbogen_two_act(_act1_candidate())
    fallen = score_ellenbogen_two_act(_act1_candidate(price_high_5y=222.0))

    assert fallen.drawdown_from_5y_high is not None
    assert fallen.drawdown_from_5y_high > TRANSITION_DRAWDOWN
    assert fallen.transition_candidate is True
    assert intact.transition_candidate is False
    assert fallen.composite == intact.composite


def test_the_structural_drawdown_is_his_own_number():
    r = score_ellenbogen_two_act(_act1_candidate(price_high_5y=300.0))
    assert r.drawdown_from_5y_high is not None
    assert r.drawdown_from_5y_high >= STRUCTURAL_DRAWDOWN
    assert r.at_structural_drawdown is True


def test_a_broken_company_is_not_a_transition_candidate():
    """The flag means "ask the question", and it is only worth asking of a
    business that is still intact. A loss-maker down 60% is not a transition,
    it is the thing the filters exist to remove."""
    r = score_ellenbogen_two_act(
        _act1_candidate(
            ebit_annual=[50.0, 20.0, -30.0, -90.0],
            ebit_ttm=-90.0,
            price_high_5y=300.0,
        )
    )
    assert not r.passed
    assert r.drawdown_from_5y_high is not None and r.drawdown_from_5y_high > 0.5
    assert r.transition_candidate is False


def test_every_row_admits_what_it_did_not_check():
    """The two acts are the framework. One of them is not in the data."""
    r = score_ellenbogen_two_act(_act1_candidate())
    assert r.act2_checked is False
    assert r.founder_act2_checked is False
    assert set(r.unchecked) == set(UNCHECKABLE_BY_DESIGN)


def test_the_gap_to_his_bar_is_reported_signed():
    """The 20% decade is the definition; the distance to it is the finding."""
    on_the_path = score_ellenbogen_two_act(_act1_candidate())
    assert on_the_path.gap_to_compounder_bar_pp is not None
    # ~25% CAGR across the window, so past his bar rather than short of it.
    assert on_the_path.gap_to_compounder_bar_pp < 0


def test_roic_series_aligns_from_the_newest_end():
    """Statements come back with different column counts often enough.

    Zipping from the oldest would compare one year's profit against another
    year's capital, silently, and the slope is the whole test.
    """
    roics = _roic_series([100.0, 150.0], [400.0, 500.0, 600.0], 0.25)
    assert len(roics) == 2
    assert roics[0] == pytest.approx(100.0 * 0.75 / 500.0)
    assert roics[1] == pytest.approx(150.0 * 0.75 / 600.0)


def test_an_errored_fetch_scores_nothing_rather_than_zero():
    r = score_ellenbogen_two_act(EllenbogenSnapshot(ticker="X", error="rate limited"))
    assert r.error == "rate limited"
    assert r.composite is None
    assert r.passed is False


def test_the_screen_is_wired_into_the_cache_and_the_api():
    assert "ellenbogen-two-act" in cache.SCREENS
    assert "ellenbogen-two-act" in SCREEN_FIELDS
    assert criteria.fingerprint("ellenbogen-two-act")


def test_the_drawdown_thresholds_are_in_the_fingerprint():
    """They decide which rows carry the flag, so a cache built under a
    different definition has to be detectable as stale."""
    crit = criteria.criteria_for("ellenbogen-two-act") or {}
    assert crit["transition_drawdown"] == TRANSITION_DRAWDOWN
    assert crit["structural_drawdown"] == STRUCTURAL_DRAWDOWN
