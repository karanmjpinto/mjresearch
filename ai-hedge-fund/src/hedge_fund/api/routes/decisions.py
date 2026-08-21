"""Decisions — size against the book, record the call, review it later."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from hedge_fund.data.service import get_data_service
from hedge_fund.db.session import SessionLocal
from hedge_fund.decisions import assess_addition, store
from hedge_fund.portfolio.service import build_portfolio_view, get_or_create_default_account

router = APIRouter()
_ds = get_data_service()

ACTIONS = {"buy", "sell", "hold", "watch", "pass"}


def _portfolio() -> dict[str, Any]:
    with SessionLocal() as db:
        return build_portfolio_view(db, get_or_create_default_account(db).id)


def _last_price(ticker: str) -> float | None:
    try:
        df = _ds.get_price_history(ticker, days=7)
        if df is not None and not df.empty and "close" in df:
            return float(df["close"].iloc[-1])
    except Exception:
        return None
    return None


class SizeRequest(BaseModel):
    ticker: str = Field(max_length=32)
    amount: float | None = Field(default=None, gt=0, description="Cash amount to deploy")
    weight_pct: float | None = Field(
        default=None, gt=0, le=100, description="Target weight instead of an amount"
    )
    days: int = Field(default=365, ge=90, le=3650)


@router.post("/size")
async def size_position(req: SizeRequest) -> dict[str, Any]:
    """What adding this position would do to the portfolio you already hold."""
    portfolio = _portfolio()
    total = float(portfolio.get("total_value") or 0.0)

    if req.amount is None and req.weight_pct is None:
        raise HTTPException(status_code=400, detail="supply either amount or weight_pct")
    amount = req.amount if req.amount is not None else total * (req.weight_pct or 0) / 100
    if amount <= 0:
        raise HTTPException(status_code=400, detail="the position must be greater than zero")

    assessment = assess_addition(
        ticker=req.ticker,
        proposed_value=amount,
        portfolio=portfolio,
        data_service=_ds,
        days=req.days,
    )
    return {
        "assessment": assessment.as_dict(),
        "portfolio": {
            "total_value": portfolio.get("total_value"),
            "cash": portfolio.get("cash"),
            "holdings_count": portfolio.get("holdings_count"),
            "currency": portfolio.get("currency"),
            "holdings": [
                {
                    "ticker": h["ticker"],
                    "weight_pct": h["weight_pct"],
                    "market_value": h["market_value"],
                }
                for h in (portfolio.get("holdings") or [])
            ],
        },
    }


class DecisionRequest(BaseModel):
    ticker: str = Field(max_length=32)
    action: str = Field(description="buy | sell | hold | watch | pass")
    rationale: str = Field(default="", max_length=4000)
    conviction: int | None = Field(default=None, ge=0, le=100)
    stance: str | None = Field(default=None, max_length=16)
    thesis: str | None = Field(default=None, max_length=12000)
    amount: float | None = Field(default=None, gt=0)
    research_run_uid: str | None = None


@router.post("")
async def create_decision(req: DecisionRequest) -> dict[str, Any]:
    """Record a decision together with the book it was made against.

    The portfolio context is captured now, because reviewing this later against
    today's book would judge the call on information that did not exist.
    """
    action = req.action.strip().lower()
    if action not in ACTIONS:
        raise HTTPException(status_code=400, detail=f"action must be one of {sorted(ACTIONS)}")

    ticker = req.ticker.strip().upper()
    portfolio = _portfolio()
    sizing = None
    weight = None

    if req.amount:
        assessment = assess_addition(
            ticker=ticker, proposed_value=req.amount, portfolio=portfolio, data_service=_ds
        )
        sizing = assessment.as_dict()
        weight = assessment.proposed_weight_pct

    saved = store.record(
        ticker=ticker,
        action=action,
        rationale=req.rationale.strip() or None,
        conviction=req.conviction,
        stance=req.stance,
        thesis=req.thesis,
        proposed_value=req.amount,
        proposed_weight_pct=weight,
        price_at_decision=_last_price(ticker),
        sizing=sizing,
        portfolio_context={
            "total_value": portfolio.get("total_value"),
            "cash": portfolio.get("cash"),
            "holdings_count": portfolio.get("holdings_count"),
            "holdings": [
                {"ticker": h["ticker"], "weight_pct": h["weight_pct"]}
                for h in (portfolio.get("holdings") or [])
            ],
        },
        research_run_uid=req.research_run_uid,
    )
    if saved is None:
        raise HTTPException(status_code=500, detail="could not record the decision")
    return saved


@router.get("")
async def list_decisions(
    ticker: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Past decisions, each scored against the price move since."""
    rows = store.list_decisions(ticker=ticker, status=status, limit=limit)
    prices: dict[str, float | None] = {}
    for row in rows:
        t = row["ticker"]
        if t not in prices:
            prices[t] = _last_price(t)
        row["outcome"] = store.score(row, prices[t])
    return {"count": len(rows), "decisions": rows}


class ReviewRequest(BaseModel):
    review_note: str = Field(max_length=4000)
    status: str | None = Field(default=None, description="open | closed")


@router.post("/{decision_id}/review")
async def review_decision(decision_id: int, req: ReviewRequest) -> dict[str, Any]:
    """Record what you concluded on looking back."""
    if req.status and req.status not in {"open", "closed"}:
        raise HTTPException(status_code=400, detail="status must be open or closed")
    updated = store.update(
        decision_id,
        review_note=req.review_note.strip() or None,
        status=req.status,
        reviewed_at=datetime.now(UTC),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return updated
