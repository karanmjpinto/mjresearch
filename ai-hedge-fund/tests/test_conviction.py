"""Conviction as three claims that must all hold.

The arithmetic being a product rather than an average is the whole design, so
that is pinned first. The rest guards the refusals: a blank leg must never
behave like a zero or like a pass.
"""

from __future__ import annotations

import pytest

from hedge_fund.valuation.conviction import (
    ConvictionError,
    conviction,
    correction_leg,
    fair_price_leg,
    horizon_leg,
)


def _full(**over):
    """Three answered legs, each deliberately strong unless overridden."""
    args = {
        "edge_source": "business_understanding",
        "margin_of_safety_pct": 40.0,
        "verified_ratio": 1.0,
        "catalyst": "Q3 earnings",
        "catalyst_certainty": 1.0,
        "days_to_catalyst": 90.0,
        "holding_period_days": 365.0,
    }
    args.update(over)
    return [
        fair_price_leg(
            edge_source=args["edge_source"],
            margin_of_safety_pct=args["margin_of_safety_pct"],
            verified_ratio=args["verified_ratio"],
        ),
        correction_leg(catalyst=args["catalyst"], catalyst_certainty=args["catalyst_certainty"]),
        horizon_leg(
            days_to_catalyst=args["days_to_catalyst"],
            holding_period_days=args["holding_period_days"],
        ),
    ]


# ------------------------------------------------------------------
# It is a product, and that is the point
# ------------------------------------------------------------------


def test_three_strong_legs_give_high_conviction():
    r = conviction(_full())
    assert r["available"] is True
    assert r["score"] == pytest.approx(1.0)
    assert r["label"] == "high"


def test_one_weak_leg_caps_the_whole_thing():
    # A real edge and a long horizon cannot rescue a thesis with a correction
    # nobody is confident in — which an average would have hidden.
    r = conviction(_full(catalyst_certainty=0.1))
    assert r["score"] == pytest.approx(0.1)
    assert r["weakest_leg"] == "correction"


def test_a_strong_edge_does_not_carry_a_missing_catalyst():
    legs = _full(catalyst=None, catalyst_certainty=None)
    r = conviction(legs)
    assert r["available"] is False
    assert "correction" in r["unanswered"]
    assert any("What causes the correction" in q for q in r["open_questions"])


# ------------------------------------------------------------------
# Requisite 1 — the edge is a gate, not a weight
# ------------------------------------------------------------------


def test_no_named_edge_means_no_score_at_all():
    leg = fair_price_leg(edge_source=None, margin_of_safety_pct=50.0)
    assert leg.score is None
    assert any("Where does the edge come from" in q for q in leg.open_questions)


def test_an_unrecognised_edge_is_refused():
    with pytest.raises(ConvictionError, match="unknown edge source"):
        fair_price_leg(edge_source="gut_feel", margin_of_safety_pct=10.0)


def test_verification_discounts_the_claim():
    strong = fair_price_leg(
        edge_source="pricing_mistake", margin_of_safety_pct=40.0, verified_ratio=1.0
    )
    shaky = fair_price_leg(
        edge_source="pricing_mistake", margin_of_safety_pct=40.0, verified_ratio=0.5
    )
    assert shaky.score == pytest.approx((strong.score or 0) * 0.5)


def test_a_bigger_discount_stops_helping_past_the_cap():
    # Beyond about forty per cent the extra gap does not make you more right,
    # it makes the estimate more suspect.
    at_cap = fair_price_leg(edge_source="pricing_mistake", margin_of_safety_pct=40.0)
    beyond = fair_price_leg(edge_source="pricing_mistake", margin_of_safety_pct=95.0)
    assert at_cap.score == beyond.score == pytest.approx(1.0)


# ------------------------------------------------------------------
# Requisite 2 — why it corrects
# ------------------------------------------------------------------


def test_a_finite_maturity_answers_the_question_on_its_own():
    leg = correction_leg(catalyst=None, finite_maturity=True)
    assert leg.score is not None
    assert "maturity" in leg.detail["certainty_note"]


def test_illiquidity_discounts_the_correction():
    liquid = correction_leg(catalyst="earnings", catalyst_certainty=0.8, liquid=True)
    thin = correction_leg(catalyst="earnings", catalyst_certainty=0.8, liquid=False)
    assert (thin.score or 0) < (liquid.score or 0)
    assert "thin trading" in thin.detail["liquidity_note"]


def test_an_explained_friction_strengthens_it():
    plain = correction_leg(catalyst="earnings", catalyst_certainty=0.8)
    explained = correction_leg(catalyst="earnings", catalyst_certainty=0.8, friction_explained=True)
    assert (explained.score or 0) > (plain.score or 0)


# ------------------------------------------------------------------
# Requisite 3 — can you wait
# ------------------------------------------------------------------


def test_waiting_longer_than_needed_is_a_full_claim_not_a_bonus():
    assert horizon_leg(days_to_catalyst=30, holding_period_days=3650).score == pytest.approx(1.0)


def test_a_horizon_shorter_than_the_wait_scores_proportionately():
    assert horizon_leg(days_to_catalyst=400, holding_period_days=100).score == pytest.approx(0.25)


@pytest.mark.parametrize(("d", "h"), [(0, 100), (100, 0), (-5, 100)])
def test_impossible_horizons_are_refused(d, h):
    with pytest.raises(ConvictionError):
        horizon_leg(days_to_catalyst=d, holding_period_days=h)


def test_an_unanswered_horizon_asks_both_questions():
    leg = horizon_leg()
    assert leg.score is None
    assert len(leg.open_questions) == 2


# ------------------------------------------------------------------
# The weakest leg decides how the view may be expressed
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("over", "expected"),
    [
        ({"catalyst_certainty": 0.1}, "value trap"),
        ({"days_to_catalyst": 3650, "holding_period_days": 100}, "shares, not options"),
        ({"margin_of_safety_pct": 2.0}, "pair against the sector"),
    ],
)
def test_the_weakest_leg_sets_what_is_allowed(over, expected):
    r = conviction(_full(**over))
    assert expected in r["structure"]["allowed"]
    assert r["structure"]["because"]


def test_with_no_weak_leg_the_full_band_stands():
    assert "full band" in conviction(_full())["structure"]["allowed"]


# ------------------------------------------------------------------
# The humility check
# ------------------------------------------------------------------


def test_a_winning_streak_cuts_conviction_and_says_so():
    calm = conviction(_full(), recent_wins=0)
    hot = conviction(_full(), recent_wins=5)
    assert hot["score"] < calm["score"]
    assert hot["humility"]["haircut"] > 0
    assert "streak" in hot["humility"]["note"]


def test_the_haircut_is_capped():
    assert conviction(_full(), recent_wins=99)["humility"]["haircut"] == 0.25


def test_a_short_run_of_wins_is_not_a_streak():
    assert conviction(_full(), recent_wins=2)["humility"]["haircut"] == 0


def test_a_missing_requisite_is_an_error_not_a_two_legged_score():
    with pytest.raises(ConvictionError, match="missing requisite"):
        conviction(_full()[:2])
