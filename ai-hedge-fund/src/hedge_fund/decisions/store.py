"""Persist decisions, and score them against what happened next."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select

from hedge_fund.db.models import Decision
from hedge_fund.db.session import SessionLocal, init_db

logger = logging.getLogger(__name__)

_initialized = False


def _ensure_schema() -> None:
    global _initialized
    if not _initialized:
        init_db()
        _initialized = True


def _to_dict(row: Decision) -> dict[str, Any]:
    return {
        "id": row.id,
        "ticker": row.ticker,
        "action": row.action,
        "status": row.status,
        "conviction": row.conviction,
        "stance": row.stance,
        "thesis": row.thesis,
        "rationale": row.rationale,
        "proposed_value": float(row.proposed_value) if row.proposed_value is not None else None,
        "proposed_weight_pct": row.proposed_weight_pct,
        "price_at_decision": float(row.price_at_decision)
        if row.price_at_decision is not None
        else None,
        "sizing": row.sizing,
        "portfolio_context": row.portfolio_context,
        "research_run_uid": row.research_run_uid,
        "executed": row.executed,
        "transaction_id": row.transaction_id,
        "review_note": row.review_note,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def record(**fields: Any) -> dict[str, Any] | None:
    _ensure_schema()
    try:
        with SessionLocal() as session:
            for key in ("proposed_value", "price_at_decision"):
                if fields.get(key) is not None:
                    fields[key] = Decimal(str(fields[key]))
            row = Decision(**fields)
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_dict(row)
    except Exception:
        logger.exception("Failed to record decision")
        return None


def list_decisions(
    ticker: str | None = None, status: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    _ensure_schema()
    with SessionLocal() as session:
        stmt = select(Decision).order_by(desc(Decision.id))
        if ticker:
            stmt = stmt.where(Decision.ticker == ticker.upper())
        if status:
            stmt = stmt.where(Decision.status == status)
        return [_to_dict(r) for r in session.scalars(stmt.limit(max(1, min(limit, 500)))).all()]


def get(decision_id: int) -> dict[str, Any] | None:
    _ensure_schema()
    with SessionLocal() as session:
        row = session.get(Decision, decision_id)
        return _to_dict(row) if row else None


def update(decision_id: int, **fields: Any) -> dict[str, Any] | None:
    _ensure_schema()
    with SessionLocal() as session:
        row = session.get(Decision, decision_id)
        if row is None:
            return None
        for key, value in fields.items():
            if value is not None and hasattr(row, key):
                setattr(row, key, value)
        session.commit()
        session.refresh(row)
        return _to_dict(row)


def score(decision: dict[str, Any], current_price: float | None) -> dict[str, Any]:
    """What has happened since the call.

    Deliberately reports the move without grading it. A buy that is down is not
    automatically a bad decision, and a lucky win is not a good one — the point
    of reviewing is to check whether the reasoning held, which is a judgement the
    numbers can inform but not make.
    """
    entry = decision.get("price_at_decision")
    if entry in (None, 0) or current_price in (None, 0):
        return {"scored": False, "reason": "no comparable price"}

    move_pct = (current_price / entry - 1) * 100
    action = (decision.get("action") or "").lower()
    # For a pass or a sell, the counterfactual is what you avoided.
    directional = -move_pct if action in {"sell", "pass"} else move_pct
    return {
        "scored": True,
        "price_at_decision": round(entry, 4),
        "current_price": round(current_price, 4),
        "move_pct": round(move_pct, 2),
        "in_your_favour_pct": round(directional, 2),
        "note": "Direction only. Whether the reasoning held is the actual review.",
    }
