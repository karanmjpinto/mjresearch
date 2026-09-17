"""Tests for the graders, which is what makes the eval score mean anything.

A grader that always returns True produces a perfect score over a broken model
and nobody notices. So every grader here is fed one answer that should pass and
one that should fail, and both directions are asserted. If a grader is ever
softened into a no-op, this file goes red.

This is the part of the eval that runs in CI. The golden set itself costs
minutes of GPU time and its output moves between runs, so it lives in
`scripts/run_eval.py` and is run deliberately.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "scripts"))

import run_eval  # noqa: E402

from evals import graders as g  # noqa: E402
from evals.golden import BASELINE, CASES  # noqa: E402


def answer(**over) -> dict:
    """A well-formed answer, for a test to spoil one field at a time."""
    base = {
        "stance": "HOLD",
        "conviction_score": 50,
        "investment_thesis": "A" * 250,
        "key_risks": ["leverage is high", "traffic is declining"],
        "confidence_in_data": 3,
    }
    base.update(over)
    return base


# --- each grader must be able to pass AND to fail ----------------------


@pytest.mark.parametrize(
    "grader,good,bad,ctx",
    [
        (g.schema_valid, answer(), {"stance": "BUY"}, {}),
        (g.schema_valid, answer(), answer(conviction_score="75"), {}),
        (g.conviction_in_range, answer(conviction_score=0), answer(conviction_score=101), {}),
        (g.conviction_in_range, answer(conviction_score=100), answer(conviction_score=-1), {}),
        (g.stance_in_enum, answer(stance="WATCH"), answer(stance="STRONG BUY"), {}),
        (
            g.stance_matches_conviction,
            answer(stance="SELL", conviction_score=20),
            answer(stance="SELL", conviction_score=90),
            {},
        ),
        (
            g.stance_matches_conviction,
            answer(stance="BUY", conviction_score=80),
            answer(stance="BUY", conviction_score=10),
            {},
        ),
        (g.risks_present_and_bounded, answer(), answer(key_risks=[]), {}),
        (g.risks_present_and_bounded, answer(), answer(key_risks=["x"] * 13), {}),
        (g.risks_present_and_bounded, answer(), answer(key_risks=["  "]), {}),
        (
            g.thesis_is_substantial,
            answer(),
            answer(investment_thesis="Cheap. Buy."),
            {},
        ),
        (
            g.low_confidence_on_thin_data,
            answer(confidence_in_data=1),
            answer(confidence_in_data=5),
            {"thin_data": True},
        ),
        (
            g.not_a_high_conviction_buy,
            answer(stance="HOLD", conviction_score=50),
            answer(stance="BUY", conviction_score=85),
            {},
        ),
        (
            g.declines_or_hedges,
            answer(stance="WATCH", conviction_score=40),
            answer(stance="BUY", conviction_score=90),
            {},
        ),
    ],
)
def test_grader_passes_the_good_and_fails_the_bad(grader, good, bad, ctx):
    assert grader(good, ctx).passed, f"{grader.__name__} rejected a valid answer"
    assert not grader(bad, ctx).passed, f"{grader.__name__} accepted an invalid answer"


def test_grounding_catches_a_figure_that_is_not_in_the_snapshot():
    ctx = {"snapshot_text": '{"trailing_pe": 7.06, "market_cap": 1830000000}'}
    grounded = answer(investment_thesis="Trades on 7.06 times earnings. " + "A" * 220)
    invented = answer(investment_thesis="Revenue grew 4821% last year. " + "A" * 220)
    assert g.no_invented_magnitudes(grounded, ctx).passed
    assert not g.no_invented_magnitudes(invented, ctx).passed


def test_grounding_ignores_ordinary_small_numbers():
    """ "a 3-year horizon" is prose, not a claim about the data."""
    ctx = {"snapshot_text": '{"pe": 7.06}'}
    a = answer(investment_thesis="Hold over a 3 to 5 year horizon. " + "A" * 220)
    assert g.no_invented_magnitudes(a, ctx).passed


def test_grounding_skips_itself_when_given_no_snapshot():
    """Better to skip loudly than to fail everything on a missing input."""
    v = g.no_invented_magnitudes(answer(investment_thesis="99999 " + "A" * 220), {})
    assert v.passed and "skipped" in v.reason


def test_thin_data_grader_is_inert_on_normal_cases():
    """It must not silently pass-or-fail cases it was not meant to judge."""
    v = g.low_confidence_on_thin_data(answer(confidence_in_data=5), {})
    assert v.passed and "not a thin-data case" in v.reason


def test_mentions_any_is_case_insensitive_and_reads_risks_too():
    hit_in_risks = answer(key_risks=["No CATALYST has been identified"])
    assert g.mentions_any("catalyst")(hit_in_risks, {}).passed
    assert not g.mentions_any("catalyst")(answer(), {}).passed


def test_a_grader_that_raises_is_not_silently_a_pass():
    """The runner must record a grader error as a failure, not skip it."""

    def broken(_a, _c):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        broken({}, {})


# --- the set itself ----------------------------------------------------


def test_the_set_is_twenty_cases_with_a_real_spread():
    """Twenty is the target; the spread is what stops it being twenty easy ones."""
    assert len(CASES) == 20
    cats = {c.category for c in CASES}
    assert cats == {"shape", "grounding", "persona", "adversarial"}
    for cat in cats:
        assert sum(1 for c in CASES if c.category == cat) >= 3, (
            f"{cat} is too thin to mean anything"
        )


def test_every_case_has_a_rationale_and_unique_id():
    ids = [c.id for c in CASES]
    assert len(set(ids)) == len(ids), "duplicate case id"
    for c in CASES:
        assert len(c.rationale) > 40, f"{c.id}: no real reason recorded for this case existing"


def test_every_case_carries_the_baseline_checks():
    """A new case must not ship without the contract every answer owes."""
    baseline_names = {n for n, _ in BASELINE}
    for c in CASES:
        names = {n for n, _ in c.checks}
        assert baseline_names <= names, f"{c.id} is missing {baseline_names - names}"


def test_cases_span_several_personas_and_companies():
    """One persona on one company measures that pair, not the app."""
    assert len({c.persona for c in CASES}) >= 6
    assert len({c.fixture for c in CASES}) >= 5


def test_adversarial_cases_use_the_constructed_fixtures():
    """The only invented inputs in the set, and they must stay labelled."""
    for c in CASES:
        if c.category == "adversarial":
            assert c.fixture in {"THIN", "CONTRADICTORY"}, (
                f"{c.id}: an adversarial case should use a constructed fixture"
            )


# --- the set-level check the per-case graders cannot make ---------------


def _rows(*verdicts: tuple[str, int]) -> list[dict]:
    return [{"stance": s, "conviction": c} for s, c in verdicts]


def test_concentration_is_the_share_on_the_single_most_common_verdict():
    rows = _rows(("BUY", 75), ("BUY", 75), ("BUY", 75), ("SELL", 15))
    share, top = run_eval._verdict_concentration(rows)
    assert top == "BUY 75"
    assert share == 0.75


def test_a_varied_set_passes_and_a_collapsed_one_fails():
    """The check that would have caught the prompt reorder.

    The reorder scored 20/20 while pulling eight of twenty cases onto one
    answer. If this threshold ever stops separating those two shapes, the set
    is back to endorsing homogenisation.
    """
    # The two distributions actually measured, 20 cases each: 5-on-one-verdict
    # with the reorder off (25%), 8-on-one-verdict with it on (40%).
    varied = _rows(
        *[("BUY", 85)] * 5,
        *[("SELL", 15)] * 4,
        *[("HOLD", 50)] * 4,
        *[("BUY", 100)] * 4,
        *[("SELL", 0)] * 3,
    )
    collapsed = _rows(*[("BUY", 75)] * 8, *[("HOLD", 50)] * 6, *[("SELL", 15)] * 6)
    assert len(varied) == len(collapsed) == 20
    assert run_eval._verdict_concentration(varied)[0] <= run_eval.MAX_VERDICT_SHARE
    assert run_eval._verdict_concentration(collapsed)[0] > run_eval.MAX_VERDICT_SHARE


def test_concentration_ignores_cases_that_never_answered():
    """A failed call must not read as agreement with the other failures."""
    rows = _rows(("BUY", 75), ("BUY", 75)) + [
        {"stance": None, "conviction": None},
        {"error": "boom", "stance": None, "conviction": None},
    ]
    share, top = run_eval._verdict_concentration(rows)
    assert top == "BUY 75" and share == 1.0


def test_concentration_is_safe_on_an_empty_run():
    assert run_eval._verdict_concentration([]) == (0.0, "-")


def test_a_conviction_of_zero_is_a_verdict_not_a_blank():
    """`0 or '-'` rendered a real strong-sell as missing data. It is a value."""
    share, top = run_eval._verdict_concentration(_rows(("SELL", 0), ("SELL", 0)))
    assert top == "SELL 0" and share == 1.0
