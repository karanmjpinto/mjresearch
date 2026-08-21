"""Research — market data bundle + optional LLM thesis (persona/committee)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hedge_fund.agents.personas import (
    DEFAULT_COMMITTEE_PERSONAS,
    is_valid_persona,
    list_persona_ids,
)
from hedge_fund.agents.plan_agent import DEFAULT_QUESTION, run_plan_analysis
from hedge_fund.agents.research_agent import (
    run_committee_analysis,
    run_research_analysis,
)
from hedge_fund.plan import catalog
from hedge_fund.runs import get_snapshot
from hedge_fund.api.research_snapshot import assemble_research_snapshot
from hedge_fund.data.service import get_data_service
from hedge_fund.orchestration import describe_plan_graph, describe_research_graph

router = APIRouter()
_ds = get_data_service()

COMMITTEE_MAX = 8


class CheckRequest(BaseModel):
    ticker: str
    include_ai: bool = Field(
        default=False,
        description="Run LLM research (Ollama default, or OpenAI when configured)",
    )
    persona: str | None = Field(
        default=None,
        description="Investor style id (e.g. warren_buffett). Omit or 'default' for generic analyst.",
    )
    committee: bool = Field(
        default=False,
        description="Run multiple personas then portfolio-manager synthesis",
    )
    committee_personas: list[str] | None = Field(
        default=None,
        description=f"Override committee list (max {COMMITTEE_MAX}); default is a fixed set of four styles",
    )


@router.get("/personas")
async def get_personas():
    """Ids available for `persona` and `committee_personas`."""
    return {
        "personas": [{"id": pid} for pid in list_persona_ids()],
        "default_committee": list(DEFAULT_COMMITTEE_PERSONAS),
    }


@router.get("/graph")
async def get_research_graph(personas: str | None = None):
    """Return the research workflow graph (nodes + edges) for UI visualization.

    Query param `personas`: optional comma-separated persona ids — defaults to the
    standard 4-person committee. Each listed persona is expanded as its own node
    in the fan-out stage.
    """
    ids = [p.strip() for p in personas.split(",")] if personas else None
    return describe_research_graph(ids)


@router.get("/graph/plan")
async def get_plan_graph():
    """Structure of the plan-based pipeline: compile, execute, narrate, verify."""
    return describe_plan_graph()


@router.post("/check")
async def check_ticker(req: CheckRequest):
    """Aggregated research: prices, fundamentals, technicals, news; optional AI layer."""
    ticker = req.ticker.strip().upper()

    base, data_snapshot = await assemble_research_snapshot(
        ticker,
        _ds,
        price_days=30,
        end_date=None,
    )

    payload = {
        **base,
        "conviction": None,
        "analysis": None,
        "stance": None,
        "ai_error": None,
        "evaluation": None,
        "verification": None,
        "ai_model": None,
        "ai_usage": None,
        "persona_id": None,
        "dissent": None,
        "committee": None,
        "synthesis": None,
        # Present only on a committee run that split and was sent back for a
        # second look; null otherwise. See agents.research_agent.
        "refinement": None,
        "committee_round1": None,
        "dissent_round1": None,
    }

    if not req.include_ai:
        return payload

    persona = (req.persona or "").strip().lower() or None
    if persona == "default":
        persona = None
    if persona is not None and not is_valid_persona(persona):
        raise HTTPException(
            status_code=400,
            detail=f"invalid persona: {req.persona!r}. Use GET /api/research/personas",
        )

    if req.committee:
        raw_ids = req.committee_personas
        if raw_ids:
            ids = [p.strip().lower() for p in raw_ids][:COMMITTEE_MAX]
            for pid in ids:
                if pid == "default" or not is_valid_persona(pid):
                    raise HTTPException(
                        status_code=400,
                        detail=f"invalid committee persona: {pid!r}",
                    )
        else:
            ids = list(DEFAULT_COMMITTEE_PERSONAS)

        ai = await run_committee_analysis(ticker, data_snapshot, ids)
        if "error" in ai:
            payload["ai_error"] = ai
            return payload

        payload["committee"] = ai.get("committee")
        synth = ai.get("synthesis") or {}
        if "error" in synth:
            payload["ai_error"] = synth
            return payload

        analysis = synth.get("analysis") or {}
        payload["conviction"] = analysis.get("conviction_score")
        payload["stance"] = analysis.get("stance")
        payload["analysis"] = analysis.get("investment_thesis")
        payload["ai_full"] = analysis
        payload["evaluation"] = synth.get("evaluation")
        payload["verification"] = synth.get("verification")
        payload["dissent"] = ai.get("dissent")
        payload["refinement"] = ai.get("refinement")
        payload["committee_round1"] = ai.get("committee_round1")
        payload["dissent_round1"] = ai.get("dissent_round1")
        payload["ai_model"] = synth.get("model")
        payload["ai_usage"] = {"per_call": ai.get("usage_total"), "synthesis": synth.get("usage")}
        payload["synthesis"] = synth
        payload["run_uid"] = ai.get("run_uid")
        return payload

    ai = await run_research_analysis(ticker, data_snapshot, persona_id=persona)
    if "error" in ai:
        payload["ai_error"] = ai
        return payload

    analysis = ai.get("analysis") or {}
    payload["conviction"] = analysis.get("conviction_score")
    payload["stance"] = analysis.get("stance")
    payload["analysis"] = analysis.get("investment_thesis")
    payload["ai_full"] = analysis
    payload["evaluation"] = ai.get("evaluation")
    payload["verification"] = ai.get("verification")
    payload["ai_model"] = ai.get("model")
    payload["ai_usage"] = ai.get("usage")
    payload["persona_id"] = ai.get("persona_id")
    payload["run_uid"] = ai.get("run_uid")
    return payload


class PlanRequest(BaseModel):
    """Plan-based research: the model chooses metrics, the harness computes them."""

    ticker: str
    question: str = Field(
        default="",
        description=f"What to answer. Defaults to: {DEFAULT_QUESTION!r}",
    )
    style: str | None = Field(
        default=None,
        description="Investing style to reflect in metric choice and weights, e.g. 'deep value'",
    )
    clarification_answers: dict[str, str] | None = Field(
        default=None,
        description="Answers to methodology questions, keyed by clarification id",
    )
    plan_override: dict | None = Field(
        default=None,
        description="Run this exact plan instead of asking the model for one",
    )
    replay_snapshot: str | None = Field(
        default=None,
        description="Snapshot hash to analyse instead of fetching fresh data",
    )


@router.get("/metrics")
async def get_metric_catalog():
    """Every deterministic metric a plan may use, with its typed signature.

    This is the catalog shown to the planner, so it is also the complete list of
    figures an analysis can be built from.
    """
    specs = catalog()
    return {
        "count": len(specs),
        "tiers": sorted({s["tier"] for s in specs}),
        "metrics": specs,
    }


@router.post("/plan")
async def plan_ticker(req: PlanRequest):
    """Plan → execute → narrate.

    Numbers come from the metric registry, never from the model. When the plan
    computes a conviction score it replaces whatever the narrator wrote, and the
    substitution is reported in `harness_overrides`.
    """
    ticker = req.ticker.strip().upper()

    if req.replay_snapshot:
        data_snapshot = get_snapshot(req.replay_snapshot)
        if data_snapshot is None:
            raise HTTPException(status_code=404, detail=f"snapshot {req.replay_snapshot} not found")
        base = {k: v for k, v in data_snapshot.items() if k != "provenance"}
    else:
        base, data_snapshot = await assemble_research_snapshot(
            ticker, _ds, price_days=30, end_date=None
        )

    result = await run_plan_analysis(
        ticker,
        data_snapshot,
        question=req.question,
        style=req.style,
        data_service=_ds,
        clarification_answers=req.clarification_answers,
        plan_override=req.plan_override,
    )

    payload = {**base, "ticker": ticker}
    if "error" in result:
        payload["ai_error"] = result
        payload["plan"] = result.get("plan")
        payload["execution"] = result.get("execution")
        return payload

    analysis = result.get("analysis") or {}
    payload.update(
        {
            "conviction": analysis.get("conviction_score"),
            "stance": analysis.get("stance"),
            "analysis": analysis.get("investment_thesis"),
            "ai_full": analysis,
            "evaluation": result.get("evaluation"),
            "verification": result.get("verification"),
            "plan": result.get("plan"),
            "execution": result.get("execution"),
            "clarifications_pending": result.get("clarifications_pending"),
            "harness_overrides": result.get("harness_overrides"),
            "ai_model": result.get("model"),
            "planner_model": result.get("planner_model"),
            "ai_usage": result.get("usage"),
            "run_uid": result.get("run_uid"),
        }
    )
    return payload
