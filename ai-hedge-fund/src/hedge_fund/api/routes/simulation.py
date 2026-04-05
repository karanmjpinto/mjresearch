"""Historical-style simulation: price window ends on as_of_date; optional LLM."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hedge_fund.agents.personas import (
    DEFAULT_COMMITTEE_PERSONAS,
    is_valid_persona,
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

_SIM_NOTE = (
    "Price window ends on as_of_date. Fundamentals, technicals, and news may reflect "
    "the latest provider snapshot; full point-in-time fundamentals are not guaranteed."
)


class BacktestRequest(BaseModel):
    ticker: str
    as_of_date: date = Field(description="Last day included in the price window (inclusive)")
    price_lookback_days: int = Field(default=30, ge=5, le=365)
    include_ai: bool = False
    persona: str | None = Field(
        default=None,
        description="Investor style id (e.g. warren_buffett); omit or 'default' for generic analyst",
    )
    committee: bool = False
    committee_personas: list[str] | None = None


@router.post("/backtest")
async def simulation_backtest(req: BacktestRequest):
    """Build a research snapshot with price history ending on ``as_of_date``; optional AI.

    Educational / research only — not a trading system.
    """
    ticker = req.ticker.strip().upper()

    base, data_snapshot = await assemble_research_snapshot(
        ticker,
        _ds,
        price_days=req.price_lookback_days,
        end_date=req.as_of_date,
        as_of_note=_SIM_NOTE,
    )

    out: dict = {
        **base,
        "as_of_date": req.as_of_date.isoformat(),
        "simulation_note": _SIM_NOTE,
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
        return out

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
            out["ai_error"] = ai
            return out

        out["committee"] = ai.get("committee")
        synth = ai.get("synthesis") or {}
        if "error" in synth:
            out["ai_error"] = synth
            return out

        analysis = synth.get("analysis") or {}
        out["conviction"] = analysis.get("conviction_score")
        out["stance"] = analysis.get("stance")
        out["analysis"] = analysis.get("investment_thesis")
        out["ai_full"] = analysis
        out["evaluation"] = synth.get("evaluation")
        out["ai_model"] = synth.get("model")
        out["ai_usage"] = {"per_call": ai.get("usage_total"), "synthesis": synth.get("usage")}
        out["synthesis"] = synth
        return out

    ai = await run_research_analysis(ticker, data_snapshot, persona_id=persona)
    if "error" in ai:
        out["ai_error"] = ai
        return out

    analysis = ai.get("analysis") or {}
    out["conviction"] = analysis.get("conviction_score")
    out["stance"] = analysis.get("stance")
    out["analysis"] = analysis.get("investment_thesis")
    out["ai_full"] = analysis
    out["evaluation"] = ai.get("evaluation")
    out["ai_model"] = ai.get("model")
    out["ai_usage"] = ai.get("usage")
    out["persona_id"] = ai.get("persona_id")
    return out
