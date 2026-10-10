"""The compounder screen's size band, and the currency rule under it.

This screen had no market-cap filter at all. Every other test in it — ROIC
above 12%, FCF conversion above 80%, a share count that does not grow — is a
quality test that holds at any size, so the only thing making it a large-cap
screen was the universe it happened to default to. That is a bad way to encode
an intention: change one line of frontend config and the screen silently
becomes something else.

The band is now explicit. These tests protect the two ways an explicit band
can still be wrong without looking wrong: a cap compared against the band of
another currency, and a currency with no band at all passing by default.
"""

from __future__ import annotations

import pytest

from hedge_fund.screeners.acquisition_compounder import (
    CAP_BAND_BY_CURRENCY,
    AcquisitionSnapshot,
    _effective_tax_rate,
    _invested_capital_series,
    _reinvestment_rate,
    _roiic,
    cap_band,
    score_acquisition_compounder,
)


def _compounder(**over) -> AcquisitionSnapshot:
    """A name that clears every quality test, so only size can fail it."""
    base = dict(
        ticker="TEST",
        sector="Industrials",
        industry="Specialty Business Services",
        currency="USD",
        market_cap=3_000_000_000,
        revenue_cagr_5y=0.18,
        eps_cagr_5y=0.22,
        fcf_ps_cagr_5y=0.20,
        revenue_yoy=0.09,
        roic=0.19,
        fcf_conversion=1.05,
        gross_margin_trend_ok=True,
        operating_margin_trend_ok=True,
        net_debt_to_ebitda=1.4,
        interest_coverage=9.0,
        share_cagr_5y=-0.005,
        reinvestment_rate=0.55,
        roiic=0.20,
        implied_compounding=0.11,
        impairment_5y_sum=0.0,
        revenue_ttm=800_000_000,
        net_income_ttm=95_000_000,
        fcf_ttm=100_000_000,
        ebitda_ttm=160_000_000,
    )
    base.update(over)
    return AcquisitionSnapshot(**base)


def test_a_mid_cap_compounder_passes_stage_one():
    r = score_acquisition_compounder(_compounder())
    assert r.stage1_passed, r.stage1_failures


@pytest.mark.parametrize(
    "cap,expected",
    [
        (300_000_000, "market_cap_below_floor"),
        (60_000_000_000, "market_cap_above_ceiling"),
    ],
)
def test_the_band_excludes_both_ends(cap, expected):
    """The ceiling is the half that did not exist before.

    A mega cap passing every quality test is still not what this desk looks
    for, and before the band it passed with the top score.
    """
    r = score_acquisition_compounder(_compounder(market_cap=cap))
    assert not r.stage1_passed
    assert expected in r.stage1_failures


def test_a_missing_cap_fails_rather_than_passing_silently():
    r = score_acquisition_compounder(_compounder(market_cap=None))
    assert "missing_market_cap" in r.stage1_failures


def test_a_yen_cap_is_judged_against_the_yen_band():
    """¥150bn is a mid cap. Against the dollar band it is a mega cap.

    This is the failure the per-currency table exists to stop: run on the
    Japanese universe with one dollar band, every company reads as too large
    and the screen returns nothing while looking like it ran to completion.
    """
    jp = _compounder(ticker="9999.T", currency="JPY", market_cap=150_000_000_000)
    r = score_acquisition_compounder(jp)
    assert r.stage1_passed, r.stage1_failures

    # And the yen band still has ends of its own.
    too_small = score_acquisition_compounder(_compounder(currency="JPY", market_cap=10_000_000_000))
    assert "market_cap_below_floor" in too_small.stage1_failures


def test_an_unlisted_currency_is_refused_not_waved_through():
    """A currency with no band cannot be screened on size.

    Refusing names it. Defaulting to the dollar band, or to no band at all,
    would let an entire market through on a filter nobody checked.
    """
    assert cap_band("KRW") is None
    r = score_acquisition_compounder(_compounder(currency="KRW"))
    assert "cap_band_unknown_currency" in r.stage1_failures

    assert cap_band(None) is None
    assert (
        "cap_band_unknown_currency"
        in score_acquisition_compounder(_compounder(currency=None)).stage1_failures
    )


def test_the_band_uses_the_quote_currency_not_the_reporting_currency():
    """Evolution AB trades in Stockholm and reports in euro.

    yfinance gives `currency` SEK, `financialCurrency` EUR, and a `marketCap`
    of 147.7bn — which is kronor, because market cap is shares times a quoted
    price. Reading the reporting currency compared that figure against the
    €18bn ceiling and rejected a roughly €13bn company for being too large.

    A false rejection, and an invisible one: "above ceiling" is a plausible
    thing for this screen to say, so nothing looked wrong. Any issuer whose
    listing and accounts disagree hits it, which is common across European
    and Asian cross-listings — exactly the population this desk screens.
    """
    sek = _compounder(currency="SEK", market_cap=147_700_000_000)
    r = score_acquisition_compounder(sek)
    assert "market_cap_above_ceiling" not in r.stage1_failures
    assert r.stage1_passed, r.stage1_failures


def test_nordic_and_swiss_currencies_have_bands():
    """`nordic.py` has carried .ST/.CO/.HE since before this screen had a band.

    A Stockholm ticker was always reachable by search, so without a krona
    entry every Swedish company failed `cap_band_unknown_currency` — refused
    on a size filter nobody had set for it. The universe-currency test could
    not catch this: Sweden is not one of the eight shipped universes.
    """
    for ccy in ("SEK", "DKK", "NOK", "CHF"):
        assert cap_band(ccy) is not None, f"{ccy} is reachable but has no band"


def test_cap_band_lookup_is_case_insensitive():
    assert cap_band("usd") == cap_band("USD")


def test_every_band_has_a_floor_below_its_ceiling():
    for ccy, (floor, ceiling) in CAP_BAND_BY_CURRENCY.items():
        assert 0 < floor < ceiling, f"{ccy} band is inverted or non-positive"


class TestReinvestmentRunway:
    """Akre's third leg: not what the capital earns, but whether there is
    anywhere to put the next dollar at that rate.

    The screen already tested the first two legs — an extraordinary business
    (ROIC above 12%) and management who do not dilute. A high-return business
    with no runway is a dividend, not a compounding machine, and before this
    the two scored identically.
    """

    def test_the_implied_rate_is_reinvestment_times_incremental_return(self):
        """80% reinvested at 25% is a 20% compounder; the score should see it."""
        strong = score_acquisition_compounder(
            _compounder(reinvestment_rate=0.80, roiic=0.25, implied_compounding=0.20)
        )
        weak = score_acquisition_compounder(
            _compounder(reinvestment_rate=0.20, roiic=0.10, implied_compounding=0.02)
        )
        assert strong.scores["reinvestment_runway"] == 5
        assert weak.scores["reinvestment_runway"] == 1
        assert strong.total_score > weak.total_score

    def test_a_high_roic_business_with_no_runway_scores_below_one_with_a_runway(self):
        """The distinction the whole leg exists to draw.

        Both businesses earn 19% on existing capital and are identical on
        every other factor. One has somewhere to deploy, one does not.
        """
        runway = score_acquisition_compounder(_compounder(implied_compounding=0.20))
        none = score_acquisition_compounder(_compounder(implied_compounding=0.01))
        assert runway.scores["reinvestment_runway"] == 5
        assert none.scores["reinvestment_runway"] == 1
        assert runway.total_score - none.total_score == 4
        assert runway.scores["roic"] == none.scores["roic"], "same business quality"

    def test_an_unmeasurable_runway_scores_neutral_not_zero(self):
        """Absent is not short.

        `_roiic` declines to answer when the capital base barely moved,
        because the ratio would be noise. Scoring that 1 would punish a
        company for the screen's own inability to measure it.
        """
        r = score_acquisition_compounder(_compounder(implied_compounding=None))
        assert r.scores["reinvestment_runway"] == 3

    def test_the_score_is_out_of_fifty_across_ten_factors(self):
        r = score_acquisition_compounder(_compounder())
        assert len(r.scores) == 10
        assert all(1 <= v <= 5 for v in r.scores.values())
        assert sum(r.scores.values()) == r.total_score

    def test_tiers_rescaled_so_a_tier_still_means_what_it_meant(self):
        """Elite was 40/45 (89%) and is now 44/50 (88%).

        Leaving the old absolute cut-offs against a larger maximum would have
        promoted every company by roughly one tier for free: a 40 that used to
        be the elite floor is now only 80% of the maximum. Asserted as
        proportions, because that is the invariant — the absolute numbers are
        allowed to move when a factor is added, their meaning is not.
        """
        old_max, new_max = 45, 50
        for old_cut, new_cut in ((40, 44), (35, 39), (28, 31)):
            assert abs(old_cut / old_max - new_cut / new_max) < 0.02, (
                f"{new_cut}/{new_max} is not the same bar as {old_cut}/{old_max}"
            )

    def test_the_tier_boundaries_are_the_ones_the_proportions_describe(self):
        """Walk the scale and confirm each tier starts where it claims to."""
        seen = {}
        for implied in (0.01, 0.08, 0.11, 0.20):
            r = score_acquisition_compounder(_compounder(implied_compounding=implied))
            seen[r.total_score] = r.tier
        for total, tier in seen.items():
            expected = (
                "elite"
                if total >= 44
                else "strong"
                if total >= 39
                else "watch"
                if total >= 31
                else "weak"
            )
            assert tier == expected, f"{total} should be {expected}, got {tier}"


class TestRoiicGuards:
    """`_roiic` has to refuse more often than it answers, and say so."""

    def test_a_flat_capital_base_gives_no_answer(self):
        """A near-zero denominator produces an arbitrarily large ratio."""
        assert _roiic([100.0, 130.0], [1000.0, 1001.0], 0.25) is None

    def test_a_shrinking_capital_base_gives_no_answer(self):
        """Often an excellent capital-light business, but not one this ratio
        can describe. Returning a negative number would read as failure."""
        assert _roiic([100.0, 130.0], [1000.0, 800.0], 0.25) is None

    def test_a_real_increment_is_measured_after_tax(self):
        # NOPAT rises by (150-100) * 0.75 = 37.5 on 250 of new capital.
        got = _roiic([100.0, 150.0], [1000.0, 1250.0], 0.25)
        assert got == pytest.approx(37.5 / 250)

    def test_too_few_years_gives_no_answer(self):
        assert _roiic([100.0], [1000.0], 0.25) is None
        assert _roiic([], [], 0.25) is None

    def test_a_negative_or_zero_capital_base_gives_no_answer(self):
        assert _roiic([100.0, 150.0], [-50.0, 250.0], 0.25) is None

    def test_the_tax_rate_is_clamped_and_shared_with_roic(self):
        """ROIC and ROIIC must use the same tax basis or they are not
        comparable, which is the entire point of reporting both."""
        assert _effective_tax_rate(None) == 0.25
        assert _effective_tax_rate(21.0) == pytest.approx(0.21), "percent form"
        assert _effective_tax_rate(0.9) == 0.35, "clamped at the top"
        assert _effective_tax_rate(-1.0) == 0.0


def _frame(rows: dict[str, list[float]]):
    """An annual statement frame, newest column first, as yfinance returns it."""
    import pandas as pd

    cols = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"])
    return pd.DataFrame(rows, index=cols).T


class TestReinvestmentRate:
    """Capex plus acquisitions over operating cash flow.

    The row names are guesses about a third party's schema, and a wrong guess
    here fails silently in the worst way: every company returns None, the
    factor scores a universal neutral 3, and the leg does nothing while
    appearing to work. These pin the names that were verified against live
    data for ROL, STRL and TTEK.
    """

    def test_capex_and_acquisitions_are_both_counted(self):
        """For a serial acquirer the acquisitions *are* the reinvestment.

        Counting only capex would score the entire strategy this screen is
        named after as reinvesting nothing.
        """
        cf = _frame(
            {
                "Operating Cash Flow": [1000.0, 900, 800, 700],
                "Capital Expenditure": [-200.0, -180, -160, -140],
                "Net Business Purchase And Sale": [-300.0, 0, 0, 0],
            }
        )
        assert _reinvestment_rate(cf) == pytest.approx(0.5)

    def test_outflow_sign_does_not_matter(self):
        cf = _frame(
            {
                "Operating Cash Flow": [1000.0, 900, 800, 700],
                "Capital Expenditure": [250.0, 180, 160, 140],
            }
        )
        assert _reinvestment_rate(cf) == pytest.approx(0.25)

    def test_spending_more_than_it_earns_is_capped_at_one(self):
        """The excess is debt- or issuance-funded, which the leverage and
        dilution factors already judge. Letting this run to 3.0 would turn an
        over-extended balance sheet into a high reinvestment score."""
        cf = _frame(
            {
                "Operating Cash Flow": [100.0, 90, 80, 70],
                "Capital Expenditure": [-400.0, 0, 0, 0],
            }
        )
        assert _reinvestment_rate(cf) == 1.0

    def test_spending_nothing_is_zero_not_unknown(self):
        """A company that reinvests nothing is measured, not unmeasurable."""
        cf = _frame({"Operating Cash Flow": [1000.0, 900, 800, 700]})
        assert _reinvestment_rate(cf) == 0.0

    def test_negative_or_missing_operating_cash_flow_gives_no_answer(self):
        assert _reinvestment_rate(None) is None
        assert (
            _reinvestment_rate(
                _frame(
                    {
                        "Operating Cash Flow": [-50.0, 90, 80, 70],
                        "Capital Expenditure": [-10.0, 0, 0, 0],
                    }
                )
            )
            is None
        )
        assert _reinvestment_rate(_frame({"Some Other Row": [1.0, 2, 3, 4]})) is None


class TestInvestedCapitalSeries:
    def test_it_is_debt_plus_equity_less_cash(self):
        bs = _frame(
            {
                "Total Debt": [100.0, 90, 80, 70],
                "Stockholders Equity": [500.0, 450, 400, 350],
                "Cash And Cash Equivalents": [50.0, 40, 30, 20],
            }
        )
        # Oldest → newest: 70+350-20, ..., 100+500-50
        assert _invested_capital_series(bs) == [400.0, 450.0, 500.0, 550.0]

    def test_a_missing_cash_line_is_treated_as_zero_not_as_failure(self):
        """A slightly conservative invested-capital figure beats no figure."""
        bs = _frame(
            {"Total Debt": [100.0, 90, 80, 70], "Stockholders Equity": [500.0, 450, 400, 350]}
        )
        assert _invested_capital_series(bs) == [420.0, 480.0, 540.0, 600.0]

    def test_no_debt_or_equity_line_gives_nothing(self):
        assert _invested_capital_series(None) == []
        assert _invested_capital_series(_frame({"Total Debt": [1.0, 2, 3, 4]})) == []


def test_every_universe_currency_has_a_band():
    """The band table and the universe list have to agree.

    A universe whose currency has no band is a region where the size filter
    silently refuses every company — the screen runs, costs the full wait, and
    returns an empty list that reads as "nothing qualified".
    """
    # The currencies the eight shipped universes quote in.
    needed = {"USD", "JPY", "GBP", "EUR", "CAD", "AUD"}
    missing = needed - set(CAP_BAND_BY_CURRENCY)
    assert not missing, f"universes quote in {sorted(missing)} with no cap band"
