"""API surface for the plan pipeline, run history, and methodology memory."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from hedge_fund.agents.llm import LLMResult
from hedge_fund.api.main import app

client = TestClient(app)

SNAP = {
    "ticker": "AAPL",
    "price": {"current": 316.83},
    "fundamentals": {"pe_ratio": 31.2, "price_to_book": 58.3, "currency": "USD"},
    "technicals": {"rsi_14": 47.3, "sma_50": 320.0, "sma_200": 295.5, "price": 316.83},
    "news_sentiment": {"enabled": False},
}

PLAN_JSON = {
    "question": "Is AAPL attractive?",
    "nodes": [
        {"id": "val", "metric": "valuation_score", "why": "multiples"},
        {"id": "conv", "metric": "weighted_conviction", "depends_on": ["val"], "why": "composite"},
    ],
    "clarifications": [],
}

NARRATIVE = {
    "conviction_score": 88,
    "stance": "HOLD",
    "investment_thesis": "A full multiple on a high-quality franchise, leaving modest upside. " * 2,
    "bull_case": "Durable demand.",
    "bear_case": "Little valuation cushion.",
    "key_risks": ["Multiple compression"],
    "time_horizon": "long_term",
    "confidence_in_data": 3,
}


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Freeze the snapshot, the price feed, and both model calls."""
    import hedge_fund.agents.plan_agent as plan_agent
    import hedge_fund.api.routes.research as research_route

    async def fake_snapshot(ticker, ds, **kw):
        return {k: v for k, v in SNAP.items()}, dict(SNAP)

    async def fake_call_json(system, user, schema=None):
        payload = PLAN_JSON if "planning stage" in system else NARRATIVE
        return LLMResult(
            content=json.dumps(payload),
            model="stub:test",
            params={"temperature": 0.0, "seed": 7},
            prompt_sha256="h" * 64,
        )

    class FakeDS:
        def get_price_history(self, ticker, days=365, end_date=None):
            idx = pd.date_range("2025-01-01", periods=min(int(days), 400), freq="D")
            return pd.DataFrame({"close": np.linspace(100, 120, len(idx))}, index=idx)

    monkeypatch.setattr(research_route, "assemble_research_snapshot", fake_snapshot)
    monkeypatch.setattr(research_route, "_ds", FakeDS())
    monkeypatch.setattr(plan_agent, "call_json", fake_call_json)


# ----------------------------------------------------------------------
# Metric catalog
# ----------------------------------------------------------------------


def test_metric_catalog_is_served():
    r = client.get("/api/research/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 10
    assert {"load", "transform", "evaluate"} <= set(body["tiers"])


def test_catalog_entries_are_fully_described():
    for metric in client.get("/api/research/metrics").json()["metrics"]:
        assert metric["description"]
        assert metric["outputs"]


# ----------------------------------------------------------------------
# Plan endpoint
# ----------------------------------------------------------------------


def test_plan_endpoint_returns_a_computed_conviction(stub_pipeline, isolated_db):
    r = client.post("/api/research/plan", json={"ticker": "AAPL"})
    assert r.status_code == 200
    body = r.json()

    assert body["stance"] == "HOLD"
    assert body["execution"]["ok_count"] == 2
    assert body["conviction"] == body["execution"]["facts"]["conviction_score"]


def test_plan_endpoint_reports_the_harness_override(stub_pipeline, isolated_db):
    body = client.post("/api/research/plan", json={"ticker": "AAPL"}).json()
    override = body["harness_overrides"][0]
    assert override["model_said"] == 88
    assert override["harness_used"] == body["conviction"]


def test_plan_endpoint_persists_a_run(stub_pipeline, isolated_db):
    uid = client.post("/api/research/plan", json={"ticker": "AAPL"}).json()["run_uid"]
    assert uid
    run = client.get(f"/api/runs/{uid}").json()
    assert run["mode"] == "plan"
    assert run["plan"]["plan_hash"]


def test_plan_endpoint_rejects_a_bad_ticker(stub_pipeline, isolated_db):
    body = client.post("/api/research/plan", json={"ticker": "!!!"}).json()
    assert body["ai_error"]["error"] == "guardrail"


def test_replaying_an_unknown_snapshot_is_a_404(stub_pipeline, isolated_db):
    r = client.post("/api/research/plan", json={"ticker": "AAPL", "replay_snapshot": "0" * 64})
    assert r.status_code == 404


def test_a_run_can_be_replayed_from_its_stored_snapshot(stub_pipeline, isolated_db):
    first = client.post("/api/research/plan", json={"ticker": "AAPL"}).json()
    digest = client.get(f"/api/runs/{first['run_uid']}").json()["snapshot_sha256"]

    replay = client.post(
        "/api/research/plan", json={"ticker": "AAPL", "replay_snapshot": digest}
    ).json()

    assert replay["conviction"] == first["conviction"]
    diff = client.get(
        "/api/runs/compare", params={"a": first["run_uid"], "b": replay["run_uid"]}
    ).json()
    assert diff["same_snapshot"] is True
    assert diff["identical_conclusion"] is True


# ----------------------------------------------------------------------
# Run history
# ----------------------------------------------------------------------


def test_runs_list_is_empty_before_any_analysis(isolated_db):
    assert client.get("/api/runs").json()["count"] == 0


def test_missing_run_is_a_404(isolated_db):
    assert client.get("/api/runs/nope").status_code == 404


def test_comparing_missing_runs_is_a_404(isolated_db):
    assert client.get("/api/runs/compare", params={"a": "x", "b": "y"}).status_code == 404


def test_missing_snapshot_is_a_404(isolated_db):
    assert client.get(f"/api/runs/snapshot/{'0' * 64}").status_code == 404


# ----------------------------------------------------------------------
# Methodology memory
# ----------------------------------------------------------------------


LESSON = "Break case-study comparisons out by asset class rather than reporting only an aggregate."


def test_a_lesson_can_be_taught_and_listed(isolated_db):
    r = client.post("/api/methodology", json={"note": LESSON})
    assert r.status_code == 200
    assert client.get("/api/methodology").json()["count"] == 1


def test_notes_recording_data_are_refused(isolated_db):
    r = client.post("/api/methodology", json={"note": "Fair value is $316.83 per share"})
    assert r.status_code == 400
    assert "method" in r.json()["detail"]


def test_applicable_notes_respect_scope(isolated_db):
    client.post("/api/methodology", json={"note": LESSON, "scope_ticker": "AAPL"})
    assert client.get("/api/methodology/applicable", params={"ticker": "AAPL"}).json()["count"] == 1
    assert client.get("/api/methodology/applicable", params={"ticker": "MSFT"}).json()["count"] == 0


def test_applicable_endpoint_shows_the_rendered_prompt_section(isolated_db):
    client.post("/api/methodology", json={"note": LESSON})
    rendered = client.get("/api/methodology/applicable").json()["rendered"]
    assert "Learned methodology" in rendered


def test_a_note_can_be_retired(isolated_db):
    note_id = client.post("/api/methodology", json={"note": LESSON}).json()["id"]
    assert client.delete(f"/api/methodology/{note_id}").status_code == 200
    assert client.get("/api/methodology").json()["count"] == 0
    assert client.get("/api/methodology", params={"include_inactive": True}).json()["count"] == 1


def test_retiring_a_missing_note_is_a_404(isolated_db):
    assert client.delete("/api/methodology/424242").status_code == 404


def test_taught_methodology_reaches_the_prompt(stub_pipeline, isolated_db, monkeypatch):
    """A stored lesson must actually appear in the system prompt of a later run."""
    import hedge_fund.agents.plan_agent as plan_agent

    seen: list[str] = []
    original = plan_agent.call_json

    async def capture(system, user, schema=None):
        seen.append(system)
        return await original(system, user, schema)

    monkeypatch.setattr(plan_agent, "call_json", capture)

    client.post("/api/methodology", json={"note": LESSON})
    client.post("/api/research/plan", json={"ticker": "AAPL"})

    assert any(LESSON in s for s in seen)


def test_check_endpoint_exposes_verification_and_run_id(isolated_db, monkeypatch):
    """The evaluation cites verification, so the caller must be able to see it."""
    import hedge_fund.agents.research_agent as agent
    import hedge_fund.api.routes.research as research_route

    async def fake_snapshot(ticker, ds, **kw):
        return dict(SNAP), dict(SNAP)

    async def fake_call_json(system, user, schema=None):
        return LLMResult(
            content=json.dumps(
                {
                    "conviction_score": 55,
                    "stance": "HOLD",
                    "investment_thesis": "A P/E ratio of 31.2 is full for the growth on offer here today.",
                    "bull_case": "Quality franchise.",
                    "bear_case": "Rich multiple.",
                    "key_risks": ["Multiple compression"],
                    "time_horizon": "long_term",
                    "confidence_in_data": 3,
                }
            ),
            model="stub:test",
            params={"temperature": 0.0},
            prompt_sha256="h" * 64,
        )

    monkeypatch.setattr(research_route, "assemble_research_snapshot", fake_snapshot)
    monkeypatch.setattr(agent, "call_json", fake_call_json)

    body = client.post("/api/research/check", json={"ticker": "AAPL", "include_ai": True}).json()
    assert body["ai_error"] is None
    assert body["verification"]["status"] == "clean"
    assert body["verification"]["verified"] == 1
    assert body["run_uid"]


# ----------------------------------------------------------------------
# Optional enrichments degrade rather than fail
# ----------------------------------------------------------------------


def test_provider_sentiment_reports_unavailable_instead_of_404():
    """An unconfigured optional key is a state to report, not a failed request."""
    r = client.get("/api/data/sentiment/AAPL")
    assert r.status_code == 200
    body = r.json()
    if body.get("available") is False:
        assert body["reason"] == "no_provider_configured"
        assert "FinBERT" in body["detail"]
    else:
        assert body["available"] is True
