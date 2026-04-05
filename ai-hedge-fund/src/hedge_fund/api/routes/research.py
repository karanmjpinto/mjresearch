"""Research — market data bundle + optional LLM thesis (persona/committee)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hedge_fund.agents.personas import (
    DEFAULT_COMMITTEE_PERSONAS,
    is_valid_persona,
    list_persona_ids,
)
from hedge_fund.agents.research_agent import (
    run_committee_analysis,
    run_research_analysis,
)
from hedge_fund.api.research_snapshot import assemble_research_snapshot
from hedge_fund.data.service import get_data_service

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
        "ai_model": None,
        "ai_usage": None,
        "persona_id": None,
        "committee": None,
        "synthesis": None,
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
        payload["ai_model"] = synth.get("model")
        payload["ai_usage"] = {"per_call": ai.get("usage_total"), "synthesis": synth.get("usage")}
        payload["synthesis"] = synth
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
    payload["ai_model"] = ai.get("model")
    payload["ai_usage"] = ai.get("usage")
    payload["persona_id"] = ai.get("persona_id")
    return payload
