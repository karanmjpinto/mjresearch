"""Persist and retrieve research runs.

Persistence is best-effort by design: a storage failure degrades observability,
it must never fail the analysis the user asked for. Every write is wrapped, and
errors are logged rather than raised.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from hedge_fund.db.models import MethodologyNote, ResearchRun, ResearchSnapshot
from hedge_fund.db.session import SessionLocal, init_db
from hedge_fund.runs.hashing import run_key, snapshot_hash
from hedge_fund.settings import settings

logger = logging.getLogger(__name__)

_initialized = False


def _ensure_schema() -> None:
    global _initialized
    if not _initialized:
        init_db()
        _initialized = True


@dataclass
class RunRecord:
    """Everything worth persisting about one analysis."""

    ticker: str
    mode: str
    snapshot: dict[str, Any]
    persona_id: str | None = None
    committee_personas: list[str] | None = None
    model: str | None = None
    model_params: dict[str, Any] | None = None
    prompt_sha256: str | None = None
    fingerprint: str | None = None
    output: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    committee_detail: list[dict[str, Any]] | None = None
    plan: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    latency_ms: int | None = None
    error: dict[str, Any] | None = None
    methodology_note_ids: list[int] | None = field(default=None)
    replay_of: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _upsert_snapshot(session: Session, record: RunRecord) -> tuple[ResearchSnapshot, str]:
    """Return the stored snapshot row, reusing an existing one when identical."""
    digest = snapshot_hash(record.snapshot)
    existing = session.scalar(
        select(ResearchSnapshot).where(ResearchSnapshot.snapshot_sha256 == digest)
    )
    if existing is not None:
        return existing, digest

    as_of = record.snapshot.get("as_of_date")
    parsed_as_of: date | None = None
    if isinstance(as_of, str):
        try:
            parsed_as_of = date.fromisoformat(as_of)
        except ValueError:
            parsed_as_of = None

    row = ResearchSnapshot(
        snapshot_sha256=digest,
        ticker=record.ticker,
        as_of_date=parsed_as_of,
        payload={k: v for k, v in record.snapshot.items() if k != "provenance"},
        provenance=record.snapshot.get("provenance"),
    )
    session.add(row)
    session.flush()
    return row, digest


def save_run(record: RunRecord) -> str | None:
    """Persist a run. Returns its uid, or None if persistence is off or failed."""
    if not settings.research_run_persistence:
        return None
    try:
        _ensure_schema()
        with SessionLocal() as session:
            snap_row, digest = _upsert_snapshot(session, record)
            uid = str(uuid.uuid4())
            key = run_key(
                snapshot_sha256=digest,
                prompt_sha256=record.prompt_sha256 or "",
                model=record.model or "",
                params=record.model_params,
                mode=record.mode,
            )
            session.add(
                ResearchRun(
                    run_uid=uid,
                    run_key=key,
                    snapshot_id=snap_row.id,
                    snapshot_sha256=digest,
                    ticker=record.ticker,
                    mode=record.mode,
                    persona_id=record.persona_id,
                    committee_personas=record.committee_personas,
                    model=record.model,
                    model_params=record.model_params,
                    prompt_sha256=record.prompt_sha256,
                    fingerprint=record.fingerprint,
                    output=record.output,
                    evaluation=record.evaluation,
                    verification=record.verification,
                    committee_detail=record.committee_detail,
                    plan=record.plan,
                    usage=record.usage,
                    latency_ms=record.latency_ms,
                    error=record.error,
                    methodology_note_ids=record.methodology_note_ids,
                    replay_of=record.replay_of,
                )
            )
            if record.methodology_note_ids:
                _bump_note_usage(session, record.methodology_note_ids)
            session.commit()
            return uid
    except Exception:
        # Observability must not be able to break analysis.
        logger.exception("Failed to persist research run for %s", record.ticker)
        return None


def _bump_note_usage(session: Session, note_ids: list[int]) -> None:
    for note in session.scalars(select(MethodologyNote).where(MethodologyNote.id.in_(note_ids))):
        note.times_applied = (note.times_applied or 0) + 1


def _run_to_dict(row: ResearchRun, *, include_snapshot: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "run_uid": row.run_uid,
        "run_key": row.run_key,
        "snapshot_sha256": row.snapshot_sha256,
        "ticker": row.ticker,
        "mode": row.mode,
        "persona_id": row.persona_id,
        "committee_personas": row.committee_personas,
        "model": row.model,
        "model_params": row.model_params,
        "prompt_sha256": row.prompt_sha256,
        "fingerprint": row.fingerprint,
        "output": row.output,
        "evaluation": row.evaluation,
        "verification": row.verification,
        "plan": row.plan,
        "usage": row.usage,
        "latency_ms": row.latency_ms,
        "error": row.error,
        "methodology_note_ids": row.methodology_note_ids,
        "replay_of": row.replay_of,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_snapshot:
        out["committee_detail"] = row.committee_detail
        if row.snapshot is not None:
            payload = dict(row.snapshot.payload or {})
            if row.snapshot.provenance:
                payload["provenance"] = row.snapshot.provenance
            out["snapshot"] = payload
    return out


def get_run(run_uid: str, *, include_snapshot: bool = True) -> dict[str, Any] | None:
    _ensure_schema()
    with SessionLocal() as session:
        row = session.scalar(select(ResearchRun).where(ResearchRun.run_uid == run_uid))
        if row is None:
            return None
        return _run_to_dict(row, include_snapshot=include_snapshot)


def get_snapshot(snapshot_sha256: str) -> dict[str, Any] | None:
    """Rehydrate a stored snapshot for replay."""
    _ensure_schema()
    with SessionLocal() as session:
        row = session.scalar(
            select(ResearchSnapshot).where(ResearchSnapshot.snapshot_sha256 == snapshot_sha256)
        )
        if row is None:
            return None
        payload = dict(row.payload or {})
        if row.provenance:
            payload["provenance"] = row.provenance
        return payload


def list_runs(
    *,
    ticker: str | None = None,
    mode: str | None = None,
    run_key_filter: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    _ensure_schema()
    with SessionLocal() as session:
        stmt = select(ResearchRun).order_by(desc(ResearchRun.id))
        if ticker:
            stmt = stmt.where(ResearchRun.ticker == ticker.upper())
        if mode:
            stmt = stmt.where(ResearchRun.mode == mode)
        if run_key_filter:
            stmt = stmt.where(ResearchRun.run_key == run_key_filter)
        rows = session.scalars(stmt.limit(max(1, min(limit, 500)))).all()
        return [_run_to_dict(r) for r in rows]


# Output fields compared when checking whether two runs agree. Free text is
# excluded: prose varies without the conclusion changing, and it is the
# conclusion that has to be stable.
COMPARED_FIELDS = ("conviction_score", "stance", "time_horizon", "confidence_in_data")


def compare_runs(run_uid_a: str, run_uid_b: str) -> dict[str, Any]:
    """Diff two runs — the primitive an eval suite is built from."""
    a = get_run(run_uid_a, include_snapshot=False)
    b = get_run(run_uid_b, include_snapshot=False)
    if a is None or b is None:
        missing = [u for u, r in ((run_uid_a, a), (run_uid_b, b)) if r is None]
        return {"error": "run_not_found", "missing": missing}

    same_inputs = a["run_key"] == b["run_key"]
    out_a = a.get("output") or {}
    out_b = b.get("output") or {}

    field_diffs: dict[str, Any] = {}
    for f in COMPARED_FIELDS:
        if out_a.get(f) != out_b.get(f):
            field_diffs[f] = {"a": out_a.get(f), "b": out_b.get(f)}

    return {
        "a": run_uid_a,
        "b": run_uid_b,
        "same_snapshot": a["snapshot_sha256"] == b["snapshot_sha256"],
        "same_prompt": a["prompt_sha256"] == b["prompt_sha256"],
        "same_model": a["model"] == b["model"],
        "same_inputs": same_inputs,
        "identical_conclusion": not field_diffs,
        "field_diffs": field_diffs,
        # Same determined inputs but a different conclusion is the case worth
        # alerting on: it means the pipeline is not yet reproducible.
        "nondeterminism_detected": same_inputs and bool(field_diffs),
    }


def prune_runs(keep: int | None = None) -> int:
    """Trim the oldest runs beyond the retention limit. Returns rows deleted."""
    keep = keep or settings.research_run_retention
    _ensure_schema()
    with SessionLocal() as session:
        ids = session.scalars(
            select(ResearchRun.id).order_by(desc(ResearchRun.id)).offset(keep)
        ).all()
        if not ids:
            return 0
        for row in session.scalars(select(ResearchRun).where(ResearchRun.id.in_(ids))):
            session.delete(row)
        session.commit()
        return len(ids)
