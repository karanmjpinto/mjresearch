"""Persist experiments. Every one of them, kept or not."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import desc, func, select

from hedge_fund.db.models import Experiment
from hedge_fund.db.session import SessionLocal, init_db

logger = logging.getLogger(__name__)

_initialized = False


def _ensure_schema() -> None:
    global _initialized
    if not _initialized:
        init_db()
        _initialized = True


def record(**fields: Any) -> int | None:
    _ensure_schema()
    try:
        with SessionLocal() as session:
            row = Experiment(**fields)
            session.add(row)
            session.commit()
            return row.id
    except Exception:
        logger.exception("Failed to record experiment")
        return None


def _to_dict(row: Experiment) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_tag": row.run_tag,
        "seq": row.seq,
        "ticker": row.ticker,
        "strategy_id": row.strategy_id,
        "params": row.params,
        "hypothesis": row.hypothesis,
        "is_baseline": row.is_baseline,
        "kept": row.kept,
        "verdict": row.verdict,
        "in_sample": row.in_sample,
        "out_of_sample": row.out_of_sample,
        "baseline_out_of_sample": row.baseline_out_of_sample,
        "primary_metric": row.primary_metric,
        "edge_vs_baseline": row.edge_vs_baseline,
        "degradation": row.degradation,
        "hurdle": row.hurdle,
        "overfit_flag": row.overfit_flag,
        "notes": row.notes,
        "reasoning": row.reasoning,
        "error": row.error,
        "model": row.model,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_experiments(run_tag: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    _ensure_schema()
    with SessionLocal() as session:
        stmt = select(Experiment).order_by(desc(Experiment.id))
        if run_tag:
            stmt = stmt.where(Experiment.run_tag == run_tag)
        return [_to_dict(r) for r in session.scalars(stmt.limit(max(1, min(limit, 1000)))).all()]


def next_seq(run_tag: str) -> int:
    _ensure_schema()
    with SessionLocal() as session:
        current = session.scalar(
            select(func.max(Experiment.seq)).where(Experiment.run_tag == run_tag)
        )
        return int(current or 0) + 1


def trial_count(run_tag: str) -> int:
    """Non-baseline experiments tried. This drives the significance hurdle."""
    _ensure_schema()
    with SessionLocal() as session:
        return int(
            session.scalar(
                select(func.count(Experiment.id)).where(
                    Experiment.run_tag == run_tag,
                    Experiment.is_baseline.is_(False),
                    Experiment.verdict != "error",
                )
            )
            or 0
        )


def leaderboard(run_tag: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Best surviving results by out-of-sample metric."""
    _ensure_schema()
    with SessionLocal() as session:
        stmt = (
            select(Experiment)
            .where(Experiment.verdict != "error", Experiment.primary_metric.isnot(None))
            .order_by(desc(Experiment.primary_metric))
        )
        if run_tag:
            stmt = stmt.where(Experiment.run_tag == run_tag)
        return [_to_dict(r) for r in session.scalars(stmt.limit(limit)).all()]


def summarize(run_tag: str) -> dict[str, Any]:
    rows = list_experiments(run_tag, limit=1000)
    tried = [r for r in rows if not r["is_baseline"] and r["verdict"] != "error"]
    kept = [r for r in tried if r["kept"]]
    return {
        "run_tag": run_tag,
        "experiments": len(rows),
        "trials": len(tried),
        "kept": len(kept),
        "discarded": len(tried) - len(kept),
        "errors": sum(1 for r in rows if r["verdict"] == "error"),
        "overfit_flagged": sum(1 for r in tried if r["overfit_flag"]),
        "best": max(
            (r for r in tried if r["primary_metric"] is not None),
            key=lambda r: r["primary_metric"],
            default=None,
        ),
    }
