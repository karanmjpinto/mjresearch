"""The committee A/B test: the gate comes first, and the letters are undone.

Two properties make the comparison worth reading, and both are easy to lose
quietly:

  - A side that fails the hard gate must never be shown to the evaluator. Not
    "shown and discounted" — the model is not called at all. Proved here by
    replacing the evaluator's only route to a model with one that fails the
    test if it is reached.
  - The evaluator sees "Answer A" and "Answer B" in a random order. If the
    letter is turned back into the wrong side, every preference in the report
    is inverted and nothing looks wrong. Proved here in both orders.

This is the part that runs in CI. The comparison itself costs two full
committees per fixture and lives in `scripts/run_committee_ab.py`.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals import committee_ab, fixtures, pairwise  # noqa: E402
from hedge_fund.agents.llm import LLMResult  # noqa: E402
from hedge_fund.agents.workflow import DEFAULT_WORKFLOW, CommitteeWorkflow  # noqa: E402

SNAPSHOT = {"ticker": "KSS", "price": {"current": 14.25}, "fundamentals": {"debt_to_equity": 1.54}}
CHALLENGER = CommitteeWorkflow(dissent_spread_threshold=20)
PERSONAS = ["warren_buffett", "ben_graham"]


def answer(**over) -> dict:
    """A final answer that clears every hard check, to spoil one field at a time."""
    base = {
        "stance": "HOLD",
        "conviction_score": 50,
        "investment_thesis": "A levered retailer with thin interest cover. " * 6,
        "bull_case": "Cheap on book.",
        "bear_case": "Traffic is declining.",
        "key_risks": ["leverage is high", "traffic is declining"],
        "time_horizon": "long_term",
        "confidence_in_data": 3,
    }
    base.update(over)
    return base


def committee_out(analysis: dict, *, status: str = "clean", mismatched: int = 0) -> dict:
    return {
        "synthesis": {
            "analysis": analysis,
            "verification": {"status": status, "mismatched": mismatched},
            "model": "stub:synth",
        },
        "refinement": {"triggered": False},
    }


def runner(current: dict, challenger: dict):
    """A fake committee: which output you get depends only on the workflow."""
    calls: list[dict] = []

    async def run(ticker, snapshot, persona_ids, workflow=None, *, persist=True):
        calls.append({"workflow": workflow, "persist": persist, "snapshot": snapshot})
        return current if workflow == DEFAULT_WORKFLOW else challenger

    run.calls = calls  # type: ignore[attr-defined]
    return run


@pytest.fixture(autouse=True)
def fixed_fixture(monkeypatch):
    monkeypatch.setattr(fixtures, "load", lambda name: SNAPSHOT)


@pytest.fixture
def evaluator_must_not_run(monkeypatch):
    """Replace the evaluator's only route to a model with a tripwire."""

    async def tripwire(*args, **kwargs):
        raise AssertionError("a gate-failing side reached the evaluator")

    monkeypatch.setattr(pairwise, "call_json", tripwire)


def preferring(marker: str):
    """A fake evaluator model that prefers whichever answer contains `marker`.

    It reads the prompt it was actually sent, so it only knows letters — which
    is exactly the position the real model is in.
    """
    prompts: list[str] = []

    async def call(system, user, schema=None, **kwargs):
        prompts.append(user)
        head = user.split("The market data bundle")[0]
        a_block, b_block = head.split("Answer B:")
        letter = "A" if marker in a_block else "B"
        assert marker in (a_block if letter == "A" else b_block)
        return LLMResult(
            content=json.dumps(
                {"preferred": letter, "reason": f"Answer {letter} is grounded; the other is not."}
            ),
            model="stub:evaluator",
            params={},
            prompt_sha256="e" * 64,
        )

    call.prompts = prompts  # type: ignore[attr-defined]
    return call


def rng_for(order: str) -> random.Random:
    """A seeded rng that shows the challenger as the given letter."""
    for seed in range(200):
        if pairwise.assign_labels(random.Random(seed))[order] == "challenger":
            return random.Random(seed)
    raise AssertionError("no seed produced that order")


# ----------------------------------------------------------------------
# The hard gate


def test_a_sound_answer_clears_the_gate():
    gated = committee_ab.gate(committee_out(answer()), SNAPSHOT)
    assert gated["passed"] is True
    names = {c["name"] for c in gated["checks"]}
    assert {"committee-ran", "verifier", "schema", "stance-coherent"} <= names
    assert "no-invented-figures" in names


def test_a_verifier_mismatch_fails_the_gate():
    gated = committee_ab.gate(committee_out(answer(), status="mismatch", mismatched=2), SNAPSHOT)
    assert gated["passed"] is False
    failed = [c for c in gated["checks"] if not c["passed"]]
    assert [c["name"] for c in failed] == ["verifier"]
    assert "2 numeric claim" in failed[0]["reason"]


def test_a_missing_verification_report_is_not_a_pass():
    out = committee_out(answer())
    del out["synthesis"]["verification"]
    assert committee_ab.gate(out, SNAPSHOT)["passed"] is False


def test_a_golden_grader_failure_fails_the_gate():
    gated = committee_ab.gate(committee_out(answer(stance="SELL", conviction_score=90)), SNAPSHOT)
    assert gated["passed"] is False
    assert "stance-coherent" in [c["name"] for c in gated["checks"] if not c["passed"]]


def test_an_invented_figure_fails_the_gate():
    spoiled = answer(investment_thesis="Revenue of $987,654 million supports the case. " * 5)
    gated = committee_ab.gate(committee_out(spoiled), SNAPSHOT)
    assert "no-invented-figures" in [c["name"] for c in gated["checks"] if not c["passed"]]


def test_a_committee_that_errored_fails_the_gate():
    for out in (
        {"error": "committee_failed", "message": "All persona runs failed"},
        {"synthesis": {"error": "llm_unavailable", "message": "down"}},
    ):
        gated = committee_ab.gate(out, SNAPSHOT)
        assert gated["passed"] is False and gated["answer"] is None


def test_thin_fixtures_hold_the_answer_to_low_confidence(monkeypatch):
    confident = committee_out(answer(confidence_in_data=5))
    assert committee_ab.gate(confident, SNAPSHOT)["passed"] is True
    assert committee_ab.gate(confident, SNAPSHOT, thin_data=True)["passed"] is False


# ----------------------------------------------------------------------
# A gate-failing side never reaches the evaluator


@pytest.mark.parametrize(
    ("current", "challenger", "who"),
    [
        (
            committee_out(answer()),
            committee_out(answer(), status="mismatch", mismatched=1),
            "challenger",
        ),
        (
            committee_out(answer(stance="BUY", conviction_score=10)),
            committee_out(answer()),
            "current",
        ),
        (
            {"error": "committee_failed", "message": "x"},
            committee_out(answer(), status="mismatch", mismatched=3),
            "current and challenger",
        ),
    ],
)
async def test_gate_failure_is_reported_and_never_judged(
    current, challenger, who, evaluator_must_not_run
):
    run = runner(current, challenger)
    # The default judge, on purpose: the tripwire sits underneath it.
    row = await committee_ab.compare_fixture(
        "KSS", CHALLENGER, PERSONAS, rng=random.Random(1), run=run
    )
    assert row["judged"] is False
    assert row["preference"] is None
    assert row["reason"] == f"not judged: {who} failed the hard gate"
    assert "evaluator" not in row
    for side in who.split(" and "):
        assert row[side]["gate"] == "fail" and row[side]["failed_checks"]


async def test_the_tripwire_itself_fires_when_both_sides_pass(evaluator_must_not_run):
    """Otherwise the tests above would pass with a tripwire nothing can reach."""
    run = runner(committee_out(answer()), committee_out(answer()))
    row = await committee_ab.compare_fixture(
        "KSS", CHALLENGER, PERSONAS, rng=random.Random(1), run=run
    )
    assert row["judged"] is False
    assert "a gate-failing side reached the evaluator" in row["reason"]


async def test_both_sides_run_on_the_same_snapshot_and_persist_nothing():
    run = runner(committee_out(answer()), committee_out(answer(), status="mismatch"))
    await committee_ab.compare_fixture("KSS", CHALLENGER, PERSONAS, rng=random.Random(1), run=run)
    assert [c["workflow"] for c in run.calls] == [DEFAULT_WORKFLOW, CHALLENGER]
    assert all(c["snapshot"] is SNAPSHOT for c in run.calls)
    assert all(c["persist"] is False for c in run.calls)


# ----------------------------------------------------------------------
# The random order is undone correctly


def test_both_label_orders_actually_occur():
    seen = {tuple(pairwise.assign_labels(random.Random(s)).items()) for s in range(50)}
    assert seen == {
        (("A", "current"), ("B", "challenger")),
        (("A", "challenger"), ("B", "current")),
    }


def test_unblind_maps_the_letter_to_the_side():
    labels = {"A": "challenger", "B": "current"}
    assert pairwise.unblind("A", labels) == "challenger"
    assert pairwise.unblind("B", labels) == "current"
    assert pairwise.unblind("TIE", labels) == "tie"
    assert pairwise.unblind_text("Answer A cites the bundle; Answer B does not.", labels) == (
        "[challenger] cites the bundle; [current] does not."
    )


@pytest.mark.parametrize("challenger_shown_as", ["A", "B"])
@pytest.mark.parametrize("winner", ["current", "challenger"])
async def test_the_report_names_the_right_side_in_either_order(
    monkeypatch, challenger_shown_as, winner
):
    theses = {
        "current": "CURRENT-MARKER thesis. " * 12,
        "challenger": "CHALLENGER-MARKER thesis. " * 12,
    }
    run = runner(
        committee_out(answer(investment_thesis=theses["current"])),
        committee_out(answer(investment_thesis=theses["challenger"])),
    )
    model = preferring(f"{winner.upper()}-MARKER")
    monkeypatch.setattr(pairwise, "call_json", model)

    row = await committee_ab.compare_fixture(
        "KSS", CHALLENGER, PERSONAS, rng=rng_for(challenger_shown_as), run=run
    )

    assert row["judged"] is True
    assert row["preference"] == winner
    assert row["evaluator"]["labels"][challenger_shown_as] == "challenger"
    # The letter the model chose is whichever one the winner was hidden behind.
    expected_letter = (
        challenger_shown_as
        if winner == "challenger"
        else ("B" if challenger_shown_as == "A" else "A")
    )
    assert row["evaluator"]["raw_preferred"] == expected_letter
    loser = "current" if winner == "challenger" else "challenger"
    assert row["reason"] == f"[{winner}] is grounded; the other is not."
    assert f"[{loser}]" not in row["reason"]


async def test_the_evaluator_is_told_nothing_that_names_a_side():
    current = answer(investment_thesis="FIRST-MARKER " * 20)
    current["workflow"] = "SECRET-SIDE-LABEL"
    current["model"] = "SECRET-MODEL"
    model = preferring("FIRST-MARKER")

    verdict = await pairwise.judge(
        "KSS", SNAPSHOT, current, answer(), rng=random.Random(3), call=model
    )

    head = model.prompts[0].split("The market data bundle")[0]
    assert "SECRET" not in head
    assert "challenger" not in head.lower() and "current" not in head.lower()
    assert verdict["preference"] == "current"


async def test_a_tie_is_reported_as_a_tie(monkeypatch):
    async def call(system, user, schema=None, **kwargs):
        return LLMResult(
            content=json.dumps({"preferred": "TIE", "reason": "Same substance."}),
            model="stub:evaluator",
            params={},
            prompt_sha256="e" * 64,
        )

    monkeypatch.setattr(pairwise, "call_json", call)
    run = runner(committee_out(answer()), committee_out(answer()))
    row = await committee_ab.compare_fixture(
        "KSS", CHALLENGER, PERSONAS, rng=random.Random(1), run=run
    )
    assert row["judged"] is True and row["preference"] == "tie"


async def test_an_evaluator_that_cannot_answer_is_not_a_tie(monkeypatch):
    async def call(system, user, schema=None, **kwargs):
        return LLMResult(content="not json", model="stub", params={}, prompt_sha256="e" * 64)

    monkeypatch.setattr(pairwise, "call_json", call)
    run = runner(committee_out(answer()), committee_out(answer()))
    row = await committee_ab.compare_fixture(
        "KSS", CHALLENGER, PERSONAS, rng=random.Random(1), run=run
    )
    assert row["judged"] is False and row["preference"] is None
    assert row["reason"].startswith("evaluator failed")


# ----------------------------------------------------------------------
# The report


async def test_table_and_result_file_carry_gate_preference_and_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(pairwise, "call_json", preferring("CHALLENGER-MARKER"))
    good = committee_out(answer(investment_thesis="CHALLENGER-MARKER thesis. " * 12))

    async def run(ticker, snapshot, persona_ids, workflow=None, *, persist=True):
        if workflow == DEFAULT_WORKFLOW:
            return committee_out(answer())
        # The challenger breaks the gate on one fixture and is sound on the other.
        return committee_out(answer(), status="mismatch", mismatched=1) if run.n.pop() else good

    run.n = [False, True]  # type: ignore[attr-defined]
    rows = await committee_ab.compare(CHALLENGER, ["KSS", "AAPL"], PERSONAS, seed=7, run=run)

    table = committee_ab.render_table(rows)
    assert "KSS" in table and "AAPL" in table
    assert "FAIL" in table and "challenger verifier" in table
    assert "not judged: challenger failed the hard gate" in table

    summary = committee_ab.summarize(rows)
    assert summary == {
        "fixtures": 2,
        "judged": 1,
        "prefers_challenger": 1,
        "prefers_current": 0,
        "tie": 0,
        "current_failed_gate": 0,
        "challenger_failed_gate": 1,
    }

    path = tmp_path / "ab.json"
    committee_ab.write_result(
        path,
        stamp="20261012T000000Z",
        label="t",
        challenger=CHALLENGER,
        challenger_file="challenger.json",
        persona_ids=PERSONAS,
        seed=7,
        rows=rows,
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["kind"] == "committee_ab"
    assert record["changed_fields"] == ["dissent_spread_threshold"]
    assert record["summary"] == summary
    assert "no outcome signal" in record["note"]
