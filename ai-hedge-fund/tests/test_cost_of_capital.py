"""The cost of capital build-up.

One number moves a valuation more than any other, so these tests pin the
arithmetic exactly and spend the rest of their attention on what must be
refused: a missing input must never quietly become a default.
"""

from __future__ import annotations

import pytest

from hedge_fund.valuation.cost_of_capital import (
    CostOfCapitalError,
    blended_erp,
    build,
    rating_for_coverage,
)
from hedge_fund.valuation.reference import CountryRisk, Reference, ReferenceMissing, load_reference

BANDS = [
    {"coverage_from": -100.0, "coverage_to": 0.5, "rating": "D2/D", "spread": 0.19},
    {"coverage_from": 0.5, "coverage_to": 1.5, "rating": "Caa/CCC", "spread": 0.0977},
    {"coverage_from": 1.5, "coverage_to": 3.0, "rating": "Ba2/BB", "spread": 0.0300},
    {"coverage_from": 3.0, "coverage_to": 100000.0, "rating": "Aaa/AAA", "spread": 0.0040},
]


def _ref() -> Reference:
    """A small, fixed reference set, so these tests do not depend on the
    vendored files changing when someone refreshes them."""
    return Reference(
        implied_erp=0.05,
        erp_as_of_year=2025,
        tbond_rate=0.04,
        countries={
            "united states": CountryRisk("United States", "NA", "Aaa", 0.0, 0.05),
            "turkey": CountryRisk("Turkey", "EMEA", "B3", 0.09, 0.14),
        },
        country_as_of="2026-01-01",
        rating_tables={"large_cap": BANDS, "small_cap": BANDS, "financial": BANDS},
        rating_as_of="2026-01-09",
    )


# ------------------------------------------------------------------
# Synthetic rating
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("coverage", "rating"),
    [(0.0, "D2/D"), (1.0, "Caa/CCC"), (2.0, "Ba2/BB"), (50.0, "Aaa/AAA")],
)
def test_coverage_maps_to_the_published_band(coverage, rating):
    assert rating_for_coverage(coverage, BANDS)[0] == rating


def test_coverage_above_the_table_takes_the_top_band():
    # The published table is open-ended at the top; it is read that way.
    assert rating_for_coverage(10_000_000.0, BANDS)[0] == "Aaa/AAA"


def test_no_table_is_an_error_not_a_guess():
    with pytest.raises(CostOfCapitalError):
        rating_for_coverage(5.0, [])


# ------------------------------------------------------------------
# Where the revenue comes from
# ------------------------------------------------------------------


def test_no_exposure_assumes_the_united_states_and_says_so():
    erp, detail = blended_erp(None, _ref())
    assert erp == 0.05
    assert "United States" in detail["assumed"]


def test_exposure_is_weighted_and_normalised():
    # Half Turkey at 14% and half the US at 5% is 9.5%, and the weights are
    # normalised so they need not be given as fractions.
    erp, detail = blended_erp({"United States": 50, "Turkey": 50}, _ref())
    assert erp == pytest.approx(0.095)
    assert detail["weighted"]["Turkey"]["weight"] == 0.5


def test_an_unknown_country_is_refused_by_name():
    # Dropping it would understate risk, which is the one direction an error
    # here must not go.
    with pytest.raises(CostOfCapitalError, match="Ruritania"):
        blended_erp({"Ruritania": 1.0}, _ref())


def test_weights_summing_to_zero_are_refused():
    with pytest.raises(CostOfCapitalError, match="sum to zero"):
        blended_erp({"United States": 0}, _ref())


# ------------------------------------------------------------------
# The build-up
# ------------------------------------------------------------------


def test_cost_of_equity_is_riskfree_plus_beta_times_premium():
    b = build(beta=1.2, riskfree=0.04, reference=_ref())
    assert b.cost_of_equity == pytest.approx(0.04 + 1.2 * 0.05)


def test_cost_of_debt_is_the_spread_the_coverage_implies_after_tax():
    b = build(beta=1.0, riskfree=0.04, interest_coverage=2.0, tax_rate=0.25, reference=_ref())
    assert b.cost_of_debt_pre_tax == pytest.approx(0.04 + 0.03)
    assert b.cost_of_debt_after_tax == pytest.approx(0.07 * 0.75)
    assert b.inputs["synthetic_rating"] == "Ba2/BB"


def test_cost_of_capital_weights_the_two_by_the_capital_structure():
    b = build(
        beta=1.0,
        riskfree=0.04,
        interest_coverage=2.0,
        tax_rate=0.25,
        equity_value=750.0,
        debt_value=250.0,
        reference=_ref(),
    )
    assert b.wacc == pytest.approx(0.75 * 0.09 + 0.25 * 0.0525)


def test_without_coverage_there_is_a_cost_of_equity_and_an_honest_gap():
    b = build(beta=1.0, riskfree=0.04, equity_value=100.0, debt_value=10.0, reference=_ref())
    assert b.cost_of_equity > 0
    assert b.cost_of_debt_after_tax is None
    assert b.wacc is None
    assert any("interest coverage" in m for m in b.missing)


def test_without_a_capital_structure_the_weighting_is_refused_not_assumed():
    b = build(beta=1.0, riskfree=0.04, interest_coverage=5.0, reference=_ref())
    assert b.wacc is None
    assert any("market value of equity" in m for m in b.missing)


def test_beta_is_required():
    with pytest.raises(CostOfCapitalError, match="beta"):
        build(beta=None, reference=_ref())


def test_an_unknown_company_type_is_refused():
    with pytest.raises(CostOfCapitalError, match="unknown company type"):
        build(beta=1.0, company_type="conglomerate", reference=_ref())


@pytest.mark.parametrize("tax", [-0.1, 1.0, 2.0, "n/a", None])
def test_an_impossible_tax_rate_is_refused(tax):
    with pytest.raises(CostOfCapitalError, match="tax rate"):
        build(beta=1.0, tax_rate=tax, reference=_ref())


def test_the_riskfree_rate_falls_back_to_the_dataset_and_names_its_source():
    b = build(beta=1.0, reference=_ref())
    assert b.inputs["riskfree"] == 0.04
    assert "T-bond" in b.inputs["riskfree_source"]


def test_every_input_is_echoed_so_the_rate_can_be_checked():
    b = build(
        beta=1.1,
        riskfree=0.042,
        interest_coverage=4.0,
        tax_rate=0.21,
        equity_value=500.0,
        debt_value=100.0,
        reference=_ref(),
    )
    d = b.as_dict()
    for key in ("beta", "riskfree", "equity_risk_premium", "tax_rate", "reference_as_of"):
        assert key in d["inputs"]
    # The steps read as an argument, not a log.
    assert any("cost of equity =" in s for s in d["steps"])
    assert any("cost of capital =" in s for s in d["steps"])


# ------------------------------------------------------------------
# The files actually shipped
# ------------------------------------------------------------------


def test_the_vendored_reference_loads_and_is_plausible():
    ref = load_reference()
    assert 0.02 < ref.implied_erp < 0.10
    assert 0.0 < ref.tbond_rate < 0.12
    assert ref.country("united states") is not None
    assert len(ref.countries) > 100
    assert all(ref.rating_tables[t] for t in ("large_cap", "small_cap", "financial"))


def test_a_missing_reference_directory_is_an_error_not_a_default():
    with pytest.raises(ReferenceMissing):
        load_reference("/tmp/definitely-not-a-reference-dir")
