"""Conviction to concentration, and the more useful inverse.

The behaviour worth protecting is the refusal to size an unanswered chain, and
the inversion — the direction that takes a book you already hold and reports
the conviction it is implicitly claiming.
"""

from __future__ import annotations

import pytest

from hedge_fund.valuation.concentration import (
    BANDS,
    ConcentrationError,
    band_for,
    check_book,
    concentration,
    implied_conviction,
)


# --- the forward direction ---------------------------------------------------


def test_high_conviction_permits_concentration() -> None:
    b = band_for(0.8)
    assert b.max_weight_pct == 15.0
    assert "All three requisites hold" in b.because


def test_absent_conviction_permits_almost_nothing() -> None:
    b = band_for(0.01)
    assert b.max_weight_pct == 2.0
    assert "buying the sector" in b.because


def test_the_bands_are_monotone() -> None:
    """A higher conviction must never permit a smaller position."""
    weights = [band_for(c).max_weight_pct for c in (0.0, 0.05, 0.2, 0.5, 0.9, 1.0)]
    assert weights == sorted(weights)


def test_a_small_band_implies_a_book_too_wide_to_be_worth_running() -> None:
    b = band_for(0.0)
    assert b.implied_names == 50
    assert "index fund with extra steps" in b.implied_names_note


def test_a_large_band_states_the_book_it_implies() -> None:
    b = band_for(0.9)
    assert b.implied_names == 7
    assert "about 7 names" in b.implied_names_note


def test_conviction_outside_zero_to_one_is_clamped_not_refused() -> None:
    assert band_for(5.0).max_weight_pct == band_for(1.0).max_weight_pct
    assert band_for(-3.0).max_weight_pct == band_for(0.0).max_weight_pct


# --- the inverse, which is the point -----------------------------------------


def test_a_position_states_the_conviction_it_claims() -> None:
    out = implied_conviction(12.0)
    assert out["claims_at_least"] == 0.50
    assert out["off_the_scale"] is False
    assert "claims conviction of at least 0.50" in out["finding"]


def test_a_small_position_claims_almost_nothing() -> None:
    assert implied_conviction(1.5)["claims_at_least"] == 0.0


def test_the_inverse_reports_the_smallest_band_that_fits() -> None:
    """5% fits the 8% band, so it claims 0.20 — not the 15% band's 0.50."""
    assert implied_conviction(5.0)["claims_at_least"] == 0.20
    assert implied_conviction(3.0)["claims_at_least"] == 0.05


def test_a_position_above_the_ceiling_is_off_the_scale_not_maximum_conviction() -> None:
    out = implied_conviction(25.0)
    assert out["off_the_scale"] is True
    assert out["claims_at_least"] is None
    assert "argued on its own terms" in out["finding"]


def test_a_negative_weight_is_refused() -> None:
    with pytest.raises(ConcentrationError, match="negative"):
        implied_conviction(-1.0)


def test_forward_and_inverse_agree_at_every_band_edge() -> None:
    """Sizing to a band's maximum must claim exactly that band's conviction."""
    for floor, max_weight, _ in BANDS:
        assert implied_conviction(max_weight)["claims_at_least"] == floor


# --- checking a real book ----------------------------------------------------


def test_a_book_within_its_bands_says_so() -> None:
    out = check_book({"AAPL": 6.0, "NVDA": 3.0}, stated={"AAPL": 0.3, "NVDA": 0.1})
    assert out["overclaimed"] == []
    assert "inside the band" in out["finding"]


def test_a_position_larger_than_its_research_supports_is_named() -> None:
    """The finding this module exists for."""
    out = check_book({"NVDA": 12.0}, stated={"NVDA": 0.1})
    assert out["overclaimed"] == ["NVDA"]
    row = out["rows"][0]
    assert row["overclaimed"] is True
    assert row["allowed_weight_pct"] == 4.0
    assert "larger than the case supports" in row["gap_note"]


def test_rows_come_back_largest_first() -> None:
    out = check_book({"A": 2.0, "B": 9.0, "C": 5.0})
    assert [r["ticker"] for r in out["rows"]] == ["B", "C", "A"]


def test_a_book_with_no_stated_conviction_still_reports_what_it_claims() -> None:
    out = check_book({"AAPL": 9.0})
    assert out["rows"][0]["claims_at_least"] == 0.50
    assert "overclaimed" not in out["rows"][0]


def test_an_empty_book_is_not_an_error() -> None:
    assert check_book({})["positions"] == 0


# --- the chain refuses to size an unanswered requisite -----------------------


def test_an_unanswered_chain_produces_no_size() -> None:
    out = concentration({"available": False, "open_questions": ["Where is the edge?"]})
    assert out["available"] is False
    assert "band" not in out, "an unanswered chain must not yield a position size"
    assert out["open_questions"] == ["Where is the edge?"]
    assert "not a low score" in out["reason"]


def test_an_answered_chain_yields_a_band_and_keeps_the_structure_rule() -> None:
    chain = {
        "available": True,
        "score": 0.6,
        "structure": {"allowed": "the full band is available", "because": "no weak leg"},
    }
    out = concentration(chain)
    assert out["available"] is True
    assert out["band"]["max_weight_pct"] == 15.0
    # Size without structure would invite putting the whole weight into the one
    # instrument the chain just ruled out.
    assert out["structure"]["allowed"] == "the full band is available"


def test_the_book_check_rides_along_when_weights_are_given() -> None:
    chain = {"available": True, "score": 0.6, "structure": {}}
    out = concentration(chain, weights_pct={"AAPL": 20.0})
    assert out["book"]["rows"][0]["off_the_scale"] is True


def test_a_zero_score_still_sizes_rather_than_refusing() -> None:
    """Zero is an answer — it means the chain ran and came out at nothing."""
    out = concentration({"available": True, "score": 0.0, "structure": {}})
    assert out["available"] is True
    assert out["band"]["max_weight_pct"] == 2.0


# --- the ceiling is a policy, and holds for every input ----------------------
#
# Thorp's own practice is a hard per-position cap laid on top of the sizing
# rule, f <= min(f*, k*f0) (p. 16), and he applies it to himself: a computed
# 6.22x Berkshire leverage became 2.0 because prices gap (p. 30). These tests
# exist so the cap cannot be raised by accident — only on purpose.


def test_no_conviction_however_high_breaches_the_ceiling() -> None:
    """The cap binds for every input, which is the point of a cap."""
    ceiling = max(weight for _, weight, _ in BANDS)
    for c in (0.0, 0.25, 0.5, 0.75, 1.0, 5.0, 1e9, float("inf")):
        assert band_for(c).max_weight_pct <= ceiling


def test_the_ceiling_is_the_top_band_not_some_middle_one() -> None:
    assert BANDS[0][1] == max(weight for _, weight, _ in BANDS)


def test_changing_the_ceiling_is_a_decision_someone_has_to_make() -> None:
    """A deliberate tripwire, not a tautology.

    15% is a stated policy with a written rationale in the module docstring. If
    a future edit moves it, this test should fail and send the reader to that
    rationale — an accidental ceiling is exactly what the docstring argues
    against.
    """
    assert BANDS[0][1] == 15.0, "the ceiling moved; update the docstring's reasoning too"
