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


def score(
    decision: dict[str, Any], current_price: float | None, index_price: float | None = None
) -> dict[str, Any]:
    """What has happened since the call, against zero and against the index.

    Deliberately reports the move without grading it. A buy that is down is not
    automatically a bad decision, and a lucky win is not a good one — the point
    of reviewing is to check whether the reasoning held, which is a judgement the
    numbers can inform but not make.

    `vs_index_pct` is the one calibration uses. In a rising market nearly every
    buy is up, so the raw move measures the market, not the pick; the move net of
    the benchmark over the same span is what a stock picker has to beat.
    """
    entry = decision.get("price_at_decision")
    if entry in (None, 0) or current_price in (None, 0):
        return {"scored": False, "reason": "no comparable price"}

    move_pct = (current_price / entry - 1) * 100
    action = (decision.get("action") or "").lower()
    # For a pass or a sell, the counterfactual is what you avoided.
    sign = -1 if action in {"sell", "pass"} else 1
    out: dict[str, Any] = {
        "scored": True,
        "price_at_decision": round(entry, 4),
        "current_price": round(current_price, 4),
        "move_pct": round(move_pct, 2),
        "in_your_favour_pct": round(sign * move_pct, 2),
        "benchmark": None,
        "benchmark_move_pct": None,
        "vs_index_pct": None,
        "note": "Direction only. Whether the reasoning held is the actual review.",
    }
    bench = (decision.get("portfolio_context") or {}).get("benchmark") or {}
    if bench.get("price") and index_price:
        bench_move = (index_price / bench["price"] - 1) * 100
        out["benchmark"] = bench.get("ticker")
        out["benchmark_move_pct"] = round(bench_move, 2)
        out["vs_index_pct"] = round(sign * (move_pct - bench_move), 2)
    return out


#: Conviction bands for calibration. Coarse on purpose: a personal book makes
#: tens of calls, not thousands, and finer bands would be noise.
CONVICTION_BANDS = ((0, 49), (50, 74), (75, 100))


def calibration(scored: list[dict[str, Any]]) -> dict[str, Any]:
    """Does higher conviction come before better outcomes? The north star to climb.

    Takes decisions that already carry an `outcome` from `score`. Only buy, sell
    and pass count: hold and watch are not a directional call. Every number is
    the move against the index (`vs_index_pct`), so a hit means the call beat the
    benchmark, not that the market rose. `monotonic` is True when each band's mean
    beats the band below it, and None while any band is empty, because a missing
    band proves nothing either way.
    """
    directional = [
        d
        for d in scored
        if d.get("conviction") is not None
        and (d.get("action") or "").lower() in {"buy", "sell", "pass"}
        and (d.get("outcome") or {}).get("scored")
    ]
    # shortcut: calls recorded before the index price was captured are left out, not backfilled.
    calls = [d for d in directional if d["outcome"].get("vs_index_pct") is not None]
    bands = []
    for lo, hi in CONVICTION_BANDS:
        moves = [d["outcome"]["vs_index_pct"] for d in calls if lo <= d["conviction"] <= hi]
        bands.append(
            {
                "band": f"{lo}-{hi}",
                "n": len(moves),
                "mean_vs_index_pct": round(sum(moves) / len(moves), 2) if moves else None,
                "hit_rate_pct": round(100 * sum(m > 0 for m in moves) / len(moves), 1)
                if moves
                else None,
            }
        )
    means = [b["mean_vs_index_pct"] for b in bands]
    monotonic = None if None in means else all(a < b for a, b in zip(means, means[1:]))
    hits = sum(d["outcome"]["vs_index_pct"] > 0 for d in calls)
    return {
        "n": len(calls),
        "n_without_index": len(directional) - len(calls),
        "hit_rate_pct": round(100 * hits / len(calls), 1) if calls else None,
        "bands": bands,
        "monotonic": monotonic,
    }
