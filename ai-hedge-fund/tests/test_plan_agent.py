"""The plan pipeline end to end, with the model stubbed.

These tests exist to pin the division of labour: the planner may not produce
numbers, and the narrator's numbers do not survive contact with the harness.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from hedge_fund.agents import plan_agent
from hedge_fund.agents.llm import LLMResult, LLMUnavailable


class FakeDS:
    def get_price_history(self, ticker, days=365, end_date=None):
        n = min(int(days), 600)
        idx = pd.date_range("2025-01-01", periods=n, freq="D")
        rng = np.random.default_rng(0)
        px = 100 * np.exp(np.cumsum(rng.normal(0.0006, 0.015, n)))
        return pd.DataFrame({"close": px}, index=idx)


SNAP = {
    "ticker": "AAPL",
    "price": {"current": 316.83},
    "fundamentals": {
        "pe_ratio": 31.2,
        "price_to_book": 58.3,
        "peg_ratio": 2.1,
        "52w_high": 355.0,
        "52w_low": 240.1,
        "currency": "USD",
        "sector": "Technology",
    },
    "technicals": {"rsi_14": 47.3, "sma_50": 320.0, "sma_200": 295.5, "price": 316.83},
    "news_sentiment": {"enabled": True, "aggregate": {"mean_signed": 0.12, "article_count": 5}},
}

PLAN_JSON = {
    "question": "Is AAPL attractive?",
    "nodes": [
        {"id": "val", "metric": "valuation_score", "why": "multiples"},
        {"id": "mom", "metric": "momentum", "params": {"lookback_days": 252}, "why": "trend"},
        {
            "id": "conv",
            "metric": "weighted_conviction",
            "params": {"valuation_weight": 2.0},
            "depends_on": ["val", "mom"],
            "why": "composite",
        },
    ],
    "clarifications": [
        {
            "id": "skip",
            "question": "Skip the most recent month of momentum?",
            "options": ["skip 1 month", "no skip"],
            "recommended": "skip 1 month",
            "affects": ["mom"],
        }
    ],
}

NARRATIVE = {
    "conviction_score": 99,  # deliberately disagrees with the computed value
    "stance": "BUY",
    "investment_thesis": "A quality franchise trading at a full multiple. " * 3,
    "bull_case": "Durable demand.",
    "bear_case": "Valuation leaves little room.",
    "key_risks": ["Multiple compression"],
    "time_horizon": "long_term",
    "confidence_in_data": 4,
}


def _stub_llm(monkeypatch, plan_payload=PLAN_JSON, narrative=NARRATIVE):
    """Return the plan on the first call and the narrative on the second."""
    calls: list[dict] = []

    async def fake_call_json(system, user, schema=None):
        is_planner = "planning stage" in system
        calls.append(
            {"role": "planner" if is_planner else "narrator", "system": system, "user": user}
        )
        payload = plan_payload if is_planner else narrative
        return LLMResult(
            content=json.dumps(payload),
            model="stub:test",
            params={"temperature": 0.0, "seed": 7},
            prompt_sha256="h" * 64,
        )

    monkeypatch.setattr(plan_agent, "call_json", fake_call_json)
    return calls


async def _run(monkeypatch, **kw):
    return await plan_agent.run_plan_analysis(
        "AAPL", SNAP, data_service=FakeDS(), persist=False, **kw
    )


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------


async def test_pipeline_produces_an_analysis(monkeypatch):
    _stub_llm(monkeypatch)
    out = await _run(monkeypatch)

    assert "error" not in out
    assert out["analysis"]["stance"] == "BUY"
    assert out["execution"]["ok_count"] == 3


async def test_harness_overrides_the_models_conviction(monkeypatch):
    """The computed score wins, and the substitution is recorded."""
    _stub_llm(monkeypatch)
    out = await _run(monkeypatch)

    computed = out["execution"]["facts"]["conviction_score"]
    assert out["analysis"]["conviction_score"] == computed
    assert out["analysis"]["conviction_score"] != 99

    override = out["harness_overrides"][0]
    assert override["field"] == "conviction_score"
    assert override["model_said"] == 99
    assert override["harness_used"] == computed


async def test_override_is_noted_in_the_evaluation(monkeypatch):
    _stub_llm(monkeypatch)
    out = await _run(monkeypatch)
    assert any("replaced with the value computed" in n for n in out["evaluation"]["notes"])


async def test_no_override_recorded_when_the_model_agrees(monkeypatch):
    _stub_llm(monkeypatch)
    probe = await _run(monkeypatch)
    computed = probe["execution"]["facts"]["conviction_score"]

    _stub_llm(monkeypatch, narrative={**NARRATIVE, "conviction_score": computed})
    out = await _run(monkeypatch)
    assert out["harness_overrides"] == []


# ----------------------------------------------------------------------
# Role separation
# ----------------------------------------------------------------------


async def test_planner_is_never_shown_market_values(monkeypatch):
    calls = _stub_llm(monkeypatch)
    await _run(monkeypatch)

    planner = next(c for c in calls if c["role"] == "planner")
    assert "316.83" not in planner["user"]
    assert "31.2" not in planner["user"]


async def test_narrator_receives_computed_values_and_a_no_arithmetic_rule(monkeypatch):
    calls = _stub_llm(monkeypatch)
    await _run(monkeypatch)

    narrator = next(c for c in calls if c["role"] == "narrator")
    assert "valuation_score=" in narrator["user"]
    assert "Do NOT calculate" in narrator["system"]


# ----------------------------------------------------------------------
# Clarifications
# ----------------------------------------------------------------------


async def test_unanswered_clarifications_are_surfaced(monkeypatch):
    _stub_llm(monkeypatch)
    out = await _run(monkeypatch)

    pending = out["clarifications_pending"]
    assert len(pending) == 1
    assert pending[0]["recommended"] == "skip 1 month"
    assert pending[0]["answered"] is False


async def test_answering_a_clarification_records_it(monkeypatch):
    _stub_llm(monkeypatch)
    out = await _run(monkeypatch, clarification_answers={"skip": "no skip"})

    assert out["clarifications_pending"] == []
    answered = out["plan"]["clarifications"][0]
    assert answered["answer"] == "no skip"
    assert answered["answered"] is True


async def test_unknown_clarification_ids_are_reported(monkeypatch):
    _stub_llm(monkeypatch)
    out = await _run(monkeypatch, clarification_answers={"ghost": "x"})
    assert out["unknown_clarification_ids"] == ["ghost"]


# ----------------------------------------------------------------------
# Failure handling
# ----------------------------------------------------------------------


async def test_invalid_plan_from_the_model_is_rejected(monkeypatch):
    _stub_llm(monkeypatch, plan_payload={"nodes": [{"id": "a", "metric": "invented_metric"}]})
    out = await _run(monkeypatch)

    assert out["error"] == "plan_invalid"
    assert any("unknown metric" in p for p in out["problems"])


async def test_plan_with_bad_params_is_rejected(monkeypatch):
    _stub_llm(
        monkeypatch,
        plan_payload={"nodes": [{"id": "a", "metric": "price_window", "params": {"days": -5}}]},
    )
    assert (await _run(monkeypatch))["error"] == "plan_invalid"


async def test_unreachable_model_is_reported_cleanly(monkeypatch):
    async def boom(system, user, schema=None):
        raise LLMUnavailable("ollama is not running")

    monkeypatch.setattr(plan_agent, "call_json", boom)
    out = await _run(monkeypatch)
    assert out["error"] == "llm_unavailable"


async def test_plan_override_skips_replanning(monkeypatch):
    calls = _stub_llm(monkeypatch)
    out = await _run(monkeypatch, plan_override=PLAN_JSON)

    assert [c["role"] for c in calls] == ["narrator"], "planner should not have been called"
    assert out["execution"]["ok_count"] == 3


async def test_execution_failure_short_circuits_before_narrating(monkeypatch):
    calls = _stub_llm(monkeypatch, plan_payload={"nodes": [{"id": "f", "metric": "fundamentals"}]})
    out = await plan_agent.run_plan_analysis(
        "AAPL", {"fundamentals": {"error": "no data"}}, data_service=FakeDS(), persist=False
    )
    assert out["error"] == "plan_execution_failed"
    assert not any(c["role"] == "narrator" for c in calls)


async def test_bad_ticker_is_rejected_before_any_model_call(monkeypatch):
    calls = _stub_llm(monkeypatch)
    out = await plan_agent.run_plan_analysis("not a ticker!!", SNAP, persist=False)
    assert out["error"] == "guardrail"
    assert calls == []


# ----------------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------------


async def test_run_is_persisted_with_its_plan(monkeypatch, isolated_db):
    from hedge_fund.runs import get_run

    _stub_llm(monkeypatch)
    out = await plan_agent.run_plan_analysis("AAPL", SNAP, data_service=FakeDS(), persist=True)

    stored = get_run(out["run_uid"])
    assert stored["mode"] == "plan"
    assert stored["plan"]["plan_hash"]
    assert stored["plan"]["facts"]["conviction_score"] == out["analysis"]["conviction_score"]
    assert stored["plan"]["overrides"][0]["model_said"] == 99


@pytest.mark.parametrize("question", ["", "Should I trim my position?"])
async def test_question_is_carried_through(monkeypatch, question):
    calls = _stub_llm(monkeypatch)
    await _run(monkeypatch, question=question)
    planner = next(c for c in calls if c["role"] == "planner")
    expected = question or plan_agent.DEFAULT_QUESTION
    assert expected in planner["user"]


# ----------------------------------------------------------------------
# Grounding
# ----------------------------------------------------------------------


async def test_ungrounded_narrative_is_flagged(monkeypatch):
    """Prose that cites no computed value is not a passing result."""
    vague = {
        **NARRATIVE,
        "investment_thesis": "A strong business with good momentum.",
        "bull_case": "Quality.",
        "bear_case": "Risk.",
        "key_risks": ["Competition"],
    }
    _stub_llm(monkeypatch, narrative=vague)
    out = await _run(monkeypatch)

    assert out["verification"]["status"] == "no_claims"
    assert out["evaluation"]["narrative_grounded"] is False
    assert any("cites none of the" in n for n in out["evaluation"]["notes"])


async def test_grounded_narrative_is_not_flagged(monkeypatch):
    grounded = {**NARRATIVE, "investment_thesis": "A P/E ratio of 31.2 leaves little room. " * 2}
    _stub_llm(monkeypatch, narrative=grounded)
    out = await _run(monkeypatch)
    assert out["evaluation"]["narrative_grounded"] is True


# ----------------------------------------------------------------------
# Replay
# ----------------------------------------------------------------------


async def test_replaying_a_stored_snapshot_and_plan_reproduces_the_run(monkeypatch, isolated_db):
    """The reproducibility contract: same snapshot + same plan => same run_key.

    Independently re-planning does not qualify. Each node's `why` reaches the
    narrator prompt but is excluded from plan_hash, so two separately planned
    runs can compute identically while asking different questions.
    """
    from hedge_fund.runs import compare_runs, get_run, get_snapshot

    _stub_llm(monkeypatch)
    first = await plan_agent.run_plan_analysis(
        "AAPL", SNAP, question="Is AAPL attractive?", data_service=FakeDS()
    )
    digest = get_run(first["run_uid"])["snapshot_sha256"]

    replay = await plan_agent.run_plan_analysis(
        "AAPL",
        get_snapshot(digest),
        question="Is AAPL attractive?",
        data_service=FakeDS(),
        plan_override=first["plan"],
    )

    diff = compare_runs(first["run_uid"], replay["run_uid"])
    assert diff["same_snapshot"] is True
    assert diff["same_prompt"] is True
    assert diff["same_inputs"] is True
    assert diff["identical_conclusion"] is True
    assert diff["nondeterminism_detected"] is False


async def test_a_rehydrated_snapshot_hashes_identically(monkeypatch, isolated_db):
    from hedge_fund.runs import get_run, get_snapshot
    from hedge_fund.runs.hashing import snapshot_hash

    _stub_llm(monkeypatch)
    out = await plan_agent.run_plan_analysis("AAPL", SNAP, data_service=FakeDS())
    digest = get_run(out["run_uid"])["snapshot_sha256"]

    assert snapshot_hash(get_snapshot(digest)) == digest
