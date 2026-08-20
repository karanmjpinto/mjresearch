"""Methodology memory — teach the system a better method, not a better answer."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hedge_fund.agents import memory

router = APIRouter()


class NoteRequest(BaseModel):
    note: str = Field(
        description=(
            "What should be done differently next time. Method only — no prices, "
            "amounts, or scores; those are rejected."
        ),
        max_length=memory.MAX_NOTE_CHARS,
    )
    tags: list[str] | None = None
    scope_ticker: str | None = Field(
        default=None, description="Limit to one ticker. Omit for a lesson that generalises."
    )
    scope_persona: str | None = Field(default=None, description="Limit to one investor persona")
    source_run_uid: str | None = Field(default=None, description="Run that prompted the lesson")


@router.get("")
async def get_notes(
    ticker: str | None = None,
    persona: str | None = None,
    include_inactive: bool = False,
) -> dict[str, Any]:
    notes = memory.list_notes(ticker=ticker, persona=persona, include_inactive=include_inactive)
    return {"count": len(notes), "notes": notes}


@router.get("/applicable")
async def get_applicable_notes(
    ticker: str | None = None, persona: str | None = None
) -> dict[str, Any]:
    """Exactly the notes that would be injected into a prompt for this run."""
    notes = memory.retrieve(ticker=ticker, persona=persona)
    return {
        "count": len(notes),
        "notes": notes,
        "rendered": memory.render_for_prompt(notes),
    }


@router.post("")
async def add_note(req: NoteRequest) -> dict[str, Any]:
    try:
        return memory.add_note(
            req.note,
            tags=req.tags,
            scope_ticker=req.scope_ticker,
            scope_persona=req.scope_persona,
            source_run_uid=req.source_run_uid,
        )
    except memory.MethodologyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{note_id}")
async def deactivate_note(note_id: int) -> dict[str, Any]:
    """Retire a note. The record is kept so past runs stay explainable."""
    if not memory.deactivate_note(note_id):
        raise HTTPException(status_code=404, detail="note not found")
    return {"ok": True, "id": note_id, "active": False}
