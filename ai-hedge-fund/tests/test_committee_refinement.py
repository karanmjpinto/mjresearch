"""The committee's second look, and per-stage model selection.

Two behaviours are under test. First, that a committee which splits materially
gets a rebuttal round before synthesis, and that what happened in that round is
recorded rather than absorbed. Second, that a stage can be pointed at its own
model without changing anything when no override is configured.
"""

from __future__ import annotations

import json

import pytest

from hedge_fund.agents import research_agent as agent
from hedge_fund.agents.llm import LLMResult, model_for_role
from hedge_fund.settings import settings


def _analysis(conviction: int, stance: str, thesis: str = "Thesis.") -> dict:
    return {
        "conviction_score": conviction,
        "stance": stance,
        "investment_thesis": thesis,
        "bull_case": "Bull.",
        "bear_case": "Bear.",
        "key_risks": ["Risk"],
        "time_horizon": "long_term",
        "confidence_in_data": 3,
    }


def _result(payload: dict, model: str = "stub:test") -> LLMResult:
    return LLMResult(
        content=json.dumps(payload),
        model=model,
        params={"temperature": 0.0},
        prompt_sha256="h" * 64,
    )


SNAPSHOT = {"ticker": "AAPL", "as_of_date": "2026-08-21", "fundamentals": {"pe_ratio": 31.2}}


@pytest.fixture
def no_persistence(monkeypatch):
    """The run store is exercised elsewhere; keep these tests to the loop."""
    monkeypatch.setattr(agent, "save_run", lambda record: "run-uid")


# ----------------------------------------------------------------------
# Dissent detection — the trigger


def test_wide_conviction_spread_is_material():
    committee = [
        {"persona_id": "a", "analysis": _analysis(85, "BUY")},
        {"persona_id": "b", "analysis": _analysis(40, "SELL")},
    ]
    dissent = agent.summarize_dissent(committee)
    assert dissent["conviction_spread"] == 45
    assert dissent["material_disagreement"] is True


def test_narrow_agreement_is_not_material():
    committee = [
        {"persona_id": "a", "analysis": _analysis(60, "BUY")},
        {"persona_id": "b", "analysis": _analysis(65, "BUY")},
    ]
    assert agent.summarize_dissent(committee)["material_disagreement"] is False


# ----------------------------------------------------------------------
# The rebuttal round


@pytest.mark.asyncio
async def test_split_committee_triggers_rebuttal_and_records_both_rounds(
    monkeypatch, no_persistence
):
    """A material split runs a second round; round 1 survives in the output."""
    monkeypatch.setattr(settings, "committee_refine_on_dissent", True)

    calls: list[str] = []

    async def fake_call_json(system, user, schema=None, **kwargs):
        # The rebuttal system prompt is the only one carrying the peer rules.
        if "already given your view" in system:
            calls.append("rebuttal")
            # The bear moves toward the bull after seeing the argument.
            return _result(_analysis(70, "BUY", "Moved on the margin data."))
        if "portfolio manager" in system.lower():
            calls.append("synthesis")
            return _result(_analysis(72, "BUY"))
        calls.append("persona")
        # Two personas, far apart, to force the split.
        return _result(_analysis(85, "BUY") if len(calls) % 2 else _analysis(40, "SELL"))

    monkeypatch.setattr(agent, "call_json", fake_call_json)

    out = await agent.run_committee_analysis("AAPL", SNAPSHOT, ["warren_buffett", "michael_burry"])

    assert calls.count("rebuttal") == 2, "every respondent should get a second look"
    assert out["refinement"]["triggered"] is True
    assert out["refinement"]["reason"]
    # Round 1 is preserved, not overwritten by the revision.
    assert out["committee_round1"] is not None
    assert {c["round"] for c in out["committee_round1"]} == {1}
    assert out["dissent_round1"]["material_disagreement"] is True
    # The synthesis saw the revised committee.
    assert out["dissent"]["conviction_spread"] == 0
    assert out["refinement"]["resolved"] is True


@pytest.mark.asyncio
async def test_agreeing_committee_skips_the_rebuttal(monkeypatch, no_persistence):
    """No split, no second round — the cost lands only on contested tickers."""
    monkeypatch.setattr(settings, "committee_refine_on_dissent", True)
    calls: list[str] = []

    async def fake_call_json(system, user, schema=None, **kwargs):
        if "already given your view" in system:
            calls.append("rebuttal")
            return _result(_analysis(60, "BUY"))
        if "portfolio manager" in system.lower():
            return _result(_analysis(61, "BUY"))
        return _result(_analysis(60, "BUY"))

    monkeypatch.setattr(agent, "call_json", fake_call_json)
    out = await agent.run_committee_analysis("AAPL", SNAPSHOT, ["warren_buffett", "ben_graham"])

    assert calls.count("rebuttal") == 0
    assert out["refinement"]["triggered"] is False
    assert out["committee_round1"] is None


@pytest.mark.asyncio
async def test_refinement_can_be_switched_off(monkeypatch, no_persistence):
    monkeypatch.setattr(settings, "committee_refine_on_dissent", False)
    calls: list[str] = []

    async def fake_call_json(system, user, schema=None, **kwargs):
        if "already given your view" in system:
            calls.append("rebuttal")
        if "portfolio manager" in system.lower():
            return _result(_analysis(70, "BUY"))
        return _result(_analysis(85, "BUY") if len(calls) % 2 == 0 else _analysis(30, "SELL"))

    monkeypatch.setattr(agent, "call_json", fake_call_json)
    out = await agent.run_committee_analysis("AAPL", SNAPSHOT, ["warren_buffett", "michael_burry"])

    assert calls.count("rebuttal") == 0
    assert out["refinement"]["triggered"] is False
    assert out["refinement"]["enabled"] is False


@pytest.mark.asyncio
async def test_failed_rebuttal_keeps_the_first_round_view(monkeypatch, no_persistence):
    """A broken second call must not delete an opinion already held."""
    monkeypatch.setattr(settings, "committee_refine_on_dissent", True)

    async def fake_call_json(system, user, schema=None, **kwargs):
        if "already given your view" in system:
            raise RuntimeError("provider exploded")
        if "portfolio manager" in system.lower():
            return _result(_analysis(70, "BUY"))
        return _result(_analysis(85, "BUY"))

    seen = {"n": 0}

    async def alternating(system, user, schema=None, **kwargs):
        if "already given your view" in system:
            raise RuntimeError("provider exploded")
        if "portfolio manager" in system.lower():
            return _result(_analysis(70, "BUY"))
        seen["n"] += 1
        return _result(_analysis(85, "BUY") if seen["n"] == 1 else _analysis(35, "SELL"))

    monkeypatch.setattr(agent, "call_json", alternating)
    out = await agent.run_committee_analysis("AAPL", SNAPSHOT, ["warren_buffett", "michael_burry"])

    assert out["refinement"]["triggered"] is True
    assert sorted(out["refinement"]["failed_personas"]) == ["michael_burry", "warren_buffett"]
    # Both original views survive the failed round.
    convictions = sorted(c["analysis"]["conviction_score"] for c in out["committee"])
    assert convictions == [35, 85]


@pytest.mark.asyncio
async def test_total_convergence_is_flagged_as_deference(monkeypatch, no_persistence):
    """Everyone folding at once is a warning sign, not a consensus."""
    monkeypatch.setattr(settings, "committee_refine_on_dissent", True)
    seen = {"n": 0}

    async def fake_call_json(system, user, schema=None, **kwargs):
        if "already given your view" in system:
            return _result(_analysis(75, "BUY"))  # all three land on the identical view
        if "portfolio manager" in system.lower():
            return _result(_analysis(75, "BUY"))
        seen["n"] += 1
        return _result(
            _analysis({1: 90, 2: 45, 3: 20}[seen["n"]], {1: "BUY", 2: "HOLD", 3: "SELL"}[seen["n"]])
        )

    monkeypatch.setattr(agent, "call_json", fake_call_json)
    out = await agent.run_committee_analysis(
        "AAPL", SNAPSHOT, ["warren_buffett", "ben_graham", "michael_burry"]
    )

    assert out["refinement"]["resolved"] is True
    assert out["refinement"].get("suspect_convergence") is True
    assert "deference" in out["refinement"]["note"]


# ----------------------------------------------------------------------
# Per-stage model selection


def test_no_override_configured_means_no_override_passed(monkeypatch):
    monkeypatch.setattr(settings, "llm_persona_model", None)
    monkeypatch.setattr(settings, "llm_synthesis_model", None)
    assert model_for_role("persona") is None
    assert agent._model_kwargs("persona") == {}
    assert agent._model_kwargs("synthesis") == {}


def test_configured_roles_resolve_independently(monkeypatch):
    monkeypatch.setattr(settings, "llm_persona_model", "qwen3:8b")
    monkeypatch.setattr(settings, "llm_synthesis_model", "qwen3:30b")
    assert agent._model_kwargs("persona") == {"model": "qwen3:8b"}
    assert agent._model_kwargs("synthesis") == {"model": "qwen3:30b"}
    assert agent._model_kwargs("single") == {}


@pytest.mark.asyncio
async def test_personas_and_synthesis_receive_their_own_models(monkeypatch, no_persistence):
    monkeypatch.setattr(settings, "committee_refine_on_dissent", False)
    monkeypatch.setattr(settings, "llm_persona_model", "small-model")
    monkeypatch.setattr(settings, "llm_synthesis_model", "big-model")
    used: list[tuple[str, str | None]] = []

    async def fake_call_json(system, user, schema=None, *, model=None):
        stage = "synthesis" if "portfolio manager" in system.lower() else "persona"
        used.append((stage, model))
        return _result(_analysis(60, "BUY"))

    monkeypatch.setattr(agent, "call_json", fake_call_json)
    await agent.run_committee_analysis("AAPL", SNAPSHOT, ["warren_buffett", "ben_graham"])

    assert ("persona", "small-model") in used
    assert ("synthesis", "big-model") in used
