"""The committee workflow object: the default must be the shipped behaviour.

The object exists so a change to a dissent threshold or a rebuttal rule can be
tested on a fixed input. That is only safe if passing nothing, and passing the
default, are the same run to the byte — otherwise adding the seam has itself
moved the committee, and every comparison made through it is against a baseline
that no longer exists.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from hedge_fund.agents import research_agent as agent
from hedge_fund.agents.llm import LLMResult, model_for_role
from hedge_fund.agents.personas import (
    REBUTTAL_RULES,
    SYNTHESIS_SYSTEM,
    get_persona_system_prompt,
    get_rebuttal_system_prompt,
)
from hedge_fund.agents.workflow import DEFAULT_WORKFLOW, CommitteeWorkflow, load_workflow
from hedge_fund.settings import settings

SNAPSHOT = {"ticker": "AAPL", "as_of_date": "2026-08-21", "fundamentals": {"pe_ratio": 31.2}}
PERSONAS = ["warren_buffett", "michael_burry"]


def _analysis(conviction: int, stance: str) -> dict:
    return {
        "conviction_score": conviction,
        "stance": stance,
        "investment_thesis": "Thesis.",
        "bull_case": "Bull.",
        "bear_case": "Bear.",
        "key_risks": ["Risk"],
        "time_horizon": "long_term",
        "confidence_in_data": 3,
    }


def _result(payload: dict) -> LLMResult:
    return LLMResult(
        content=json.dumps(payload),
        model="stub:test",
        params={"temperature": 0.0},
        prompt_sha256="h" * 64,
    )


def _recording_llm(first_round: dict[str, tuple[int, str]]):
    """A fake model that records every prompt it is sent, in order."""
    seen: list[tuple[str, str]] = []

    async def fake_call_json(system, user, schema=None, **kwargs):
        seen.append((system, user))
        for pid, (conviction, stance) in first_round.items():
            if get_persona_system_prompt(pid) in system:
                return _result(_analysis(conviction, stance))
        return _result(_analysis(55, "HOLD"))

    return fake_call_json, seen


SPLIT = {"warren_buffett": (85, "BUY"), "michael_burry": (20, "SELL")}


@pytest.fixture
def no_persistence(monkeypatch):
    monkeypatch.setattr(agent, "save_run", lambda record: "run-uid")
    monkeypatch.setattr(settings, "committee_refine_on_dissent", True)


# ----------------------------------------------------------------------
# The default is the shipped behaviour


def test_default_carries_the_shipped_constants():
    assert DEFAULT_WORKFLOW.dissent_spread_threshold == 30
    assert DEFAULT_WORKFLOW.dissent_max_stances == 2
    assert DEFAULT_WORKFLOW.rebuttal_rules == REBUTTAL_RULES
    assert DEFAULT_WORKFLOW.synthesis_system == SYNTHESIS_SYSTEM
    assert DEFAULT_WORKFLOW.changed_fields() == []


def test_default_rebuttal_prompt_is_unchanged():
    pid = "warren_buffett"
    expected = f"{get_persona_system_prompt(pid)}\n{REBUTTAL_RULES.strip()}"
    assert get_rebuttal_system_prompt(pid) == expected
    assert get_rebuttal_system_prompt(pid, DEFAULT_WORKFLOW.rebuttal_rules) == expected


async def test_no_workflow_and_default_workflow_send_identical_prompts(monkeypatch, no_persistence):
    """Every prompt of a split committee — personas, rebuttals, synthesis."""
    runs = []
    outs = []
    for workflow in (None, DEFAULT_WORKFLOW, CommitteeWorkflow()):
        fake, seen = _recording_llm(SPLIT)
        monkeypatch.setattr(agent, "call_json", fake)
        args = (workflow,) if workflow is not None else ()
        outs.append(await agent.run_committee_analysis("AAPL", SNAPSHOT, PERSONAS, *args))
        runs.append(sorted(seen))

    # Two personas, two rebuttals, one synthesis — the rebuttal path really ran.
    assert len(runs[0]) == 5
    assert outs[0]["refinement"]["triggered"] is True
    assert runs[0] == runs[1] == runs[2]
    assert outs[0]["dissent"] == outs[1]["dissent"] == outs[2]["dissent"]
    assert any(SYNTHESIS_SYSTEM in system for system, _ in runs[0])
    assert sum(REBUTTAL_RULES.strip() in system for system, _ in runs[0]) == 2


# ----------------------------------------------------------------------
# A challenger moves exactly what it names


def test_spread_threshold_decides_what_counts_as_a_split():
    committee = [
        {"persona_id": "a", "analysis": _analysis(70, "BUY")},
        {"persona_id": "b", "analysis": _analysis(45, "HOLD")},
    ]
    assert agent.summarize_dissent(committee)["material_disagreement"] is False
    tighter = CommitteeWorkflow(dissent_spread_threshold=20)
    assert agent.summarize_dissent(committee, tighter)["material_disagreement"] is True


def test_stance_count_decides_what_counts_as_a_split():
    committee = [
        {"persona_id": "a", "analysis": _analysis(55, "BUY")},
        {"persona_id": "b", "analysis": _analysis(50, "HOLD")},
    ]
    assert agent.summarize_dissent(committee)["material_disagreement"] is False
    stricter = CommitteeWorkflow(dissent_max_stances=1)
    assert agent.summarize_dissent(committee, stricter)["material_disagreement"] is True


async def test_challenger_rules_reach_the_rebuttal_and_the_synthesis(monkeypatch, no_persistence):
    challenger = CommitteeWorkflow(
        rebuttal_rules="CHALLENGER REBUTTAL RULES", synthesis_system="CHALLENGER SYNTHESIS"
    )
    fake, seen = _recording_llm(SPLIT)
    monkeypatch.setattr(agent, "call_json", fake)

    await agent.run_committee_analysis("AAPL", SNAPSHOT, PERSONAS, challenger)

    systems = [system for system, _ in seen]
    assert sum("CHALLENGER REBUTTAL RULES" in s for s in systems) == 2
    assert sum(s.startswith("CHALLENGER SYNTHESIS") for s in systems) == 1
    assert not any(REBUTTAL_RULES.strip() in s for s in systems)
    assert not any(SYNTHESIS_SYSTEM in s for s in systems)


async def test_a_higher_threshold_skips_the_rebuttal(monkeypatch, no_persistence):
    fake, seen = _recording_llm(SPLIT)
    monkeypatch.setattr(agent, "call_json", fake)
    lax = CommitteeWorkflow(dissent_spread_threshold=100, dissent_max_stances=4)

    out = await agent.run_committee_analysis("AAPL", SNAPSHOT, PERSONAS, lax)

    assert out["refinement"]["triggered"] is False
    assert len(seen) == 3  # two personas and the synthesis; nobody was called back


async def test_persist_false_leaves_nothing_in_the_run_store(monkeypatch):
    saved = []
    monkeypatch.setattr(agent, "save_run", lambda record: saved.append(record) or "run-uid")
    fake, _ = _recording_llm({"warren_buffett": (60, "BUY"), "michael_burry": (55, "BUY")})
    monkeypatch.setattr(agent, "call_json", fake)

    out = await agent.run_committee_analysis("AAPL", SNAPSHOT, PERSONAS, persist=False)
    assert out["run_uid"] is None and saved == []

    out = await agent.run_committee_analysis("AAPL", SNAPSHOT, PERSONAS)
    assert out["run_uid"] == "run-uid" and len(saved) == 1


# ----------------------------------------------------------------------
# The challenger file


def test_challenger_file_overrides_only_what_it_names(tmp_path):
    path = tmp_path / "challenger.json"
    path.write_text(json.dumps({"dissent_spread_threshold": 20}), encoding="utf-8")
    wf = load_workflow(path)
    assert wf.dissent_spread_threshold == 20
    assert wf.rebuttal_rules == REBUTTAL_RULES
    assert wf.changed_fields() == ["dissent_spread_threshold"]


def test_a_misspelt_field_fails_instead_of_comparing_the_default_to_itself(tmp_path):
    path = tmp_path / "challenger.json"
    path.write_text(json.dumps({"dissent_spread_treshold": 20}), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_workflow(path)


def test_a_file_that_is_not_an_object_is_refused(tmp_path):
    path = tmp_path / "challenger.json"
    path.write_text("[30]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_workflow(path)


# ----------------------------------------------------------------------
# The evaluator's model


def test_evaluator_role_is_absent_until_configured(monkeypatch):
    monkeypatch.setattr(settings, "llm_evaluator_model", None)
    assert model_for_role("evaluator") is None
    monkeypatch.setattr(settings, "llm_evaluator_model", "qwen3:30b")
    assert model_for_role("evaluator") == "qwen3:30b"
    assert model_for_role("persona") == (settings.llm_persona_model or None)
