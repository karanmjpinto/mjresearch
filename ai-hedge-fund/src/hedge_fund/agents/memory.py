"""Methodology memory — corrections of *method*, carried between runs.

When an analysis comes out wrong, the durable lesson is rarely the number. It is
the approach: break case studies out by asset class rather than reporting an
aggregate; discount reported margins when a one-off gain inflates them; treat a
sub-3-year price history as insufficient for a trend claim. Those lessons
generalise across tickers, and they are what a junior analyst actually absorbs.

Two constraints follow from that, both deliberate:

* **Only method text is stored.** Never chat history, never the snapshot, never
  the figures from the run that prompted the note. This keeps the corpus
  portable, reviewable by a human, and safe to apply to a different name.
* **Notes are retrieved, not accumulated.** Only notes matching the current
  ticker/persona scope enter the prompt, and the ids used are recorded on the
  run, so any conclusion can be traced back to the guidance that shaped it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, or_, select

from hedge_fund.db.models import MethodologyNote
from hedge_fund.db.session import SessionLocal, init_db

logger = logging.getLogger(__name__)

MAX_NOTE_CHARS = 1200
MAX_NOTES_IN_PROMPT = 12

_initialized = False


def _ensure_schema() -> None:
    global _initialized
    if not _initialized:
        init_db()
        _initialized = True


class MethodologyError(ValueError):
    """The submitted note is not storable as portable methodology."""


# Patterns that indicate a note is recording data rather than method. Storing a
# number freezes a fact that was only true for one run, and it will be applied,
# wrongly, to every later one.
_DATA_LIKE = re.compile(
    r"""
    (\$\s*\d)                         # a currency amount
    | (\b\d{1,3}(,\d{3})+\b)          # a grouped figure
    | (\b\d+(\.\d+)?\s*%\s*(?:conviction|score)\b)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def scrub(note: str) -> str:
    """Normalize a note, rejecting anything that is data rather than method."""
    text = " ".join((note or "").split())
    if not text:
        raise MethodologyError("note is empty")
    if len(text) > MAX_NOTE_CHARS:
        raise MethodologyError(f"note exceeds {MAX_NOTE_CHARS} characters")
    if _DATA_LIKE.search(text):
        raise MethodologyError(
            "note looks like it records data (a price, amount, or score) rather than "
            "a method. Write what should be done differently next time instead."
        )
    return text


@dataclass
class Note:
    id: int
    note: str
    tags: list[str]
    scope_ticker: str | None
    scope_persona: str | None
    times_applied: int
    created_at: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "note": self.note,
            "tags": self.tags,
            "scope_ticker": self.scope_ticker,
            "scope_persona": self.scope_persona,
            "times_applied": self.times_applied,
            "created_at": self.created_at,
        }


def _to_note(row: MethodologyNote) -> Note:
    return Note(
        id=row.id,
        note=row.note,
        tags=list(row.tags or []),
        scope_ticker=row.scope_ticker,
        scope_persona=row.scope_persona,
        times_applied=row.times_applied or 0,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


def add_note(
    note: str,
    *,
    tags: list[str] | None = None,
    scope_ticker: str | None = None,
    scope_persona: str | None = None,
    source_run_uid: str | None = None,
) -> dict[str, Any]:
    """Store one methodology lesson. Raises :class:`MethodologyError` if unusable."""
    text = scrub(note)
    _ensure_schema()
    with SessionLocal() as session:
        row = MethodologyNote(
            note=text,
            tags=[t.strip().lower() for t in (tags or []) if t.strip()],
            scope_ticker=(scope_ticker or "").strip().upper() or None,
            scope_persona=(scope_persona or "").strip().lower() or None,
            source_run_uid=source_run_uid,
            active=True,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_note(row).as_dict()


def list_notes(
    *, ticker: str | None = None, persona: str | None = None, include_inactive: bool = False
) -> list[dict[str, Any]]:
    _ensure_schema()
    with SessionLocal() as session:
        stmt = select(MethodologyNote).order_by(desc(MethodologyNote.id))
        if not include_inactive:
            stmt = stmt.where(MethodologyNote.active.is_(True))
        if ticker:
            stmt = stmt.where(
                or_(
                    MethodologyNote.scope_ticker.is_(None),
                    MethodologyNote.scope_ticker == ticker.upper(),
                )
            )
        if persona:
            stmt = stmt.where(
                or_(
                    MethodologyNote.scope_persona.is_(None),
                    MethodologyNote.scope_persona == persona.lower(),
                )
            )
        return [_to_note(r).as_dict() for r in session.scalars(stmt).all()]


def deactivate_note(note_id: int) -> bool:
    """Retire a note without destroying the record of it having been applied."""
    _ensure_schema()
    with SessionLocal() as session:
        row = session.get(MethodologyNote, note_id)
        if row is None:
            return False
        row.active = False
        session.commit()
        return True


def retrieve(
    *, ticker: str | None = None, persona: str | None = None, limit: int = MAX_NOTES_IN_PROMPT
) -> list[dict[str, Any]]:
    """Notes applicable to this run: global ones plus those scoped to it.

    Ticker- and persona-scoped notes sort ahead of global ones so that when the
    limit bites, the most specific guidance survives.
    """
    try:
        notes = list_notes(ticker=ticker, persona=persona)
    except Exception:
        logger.exception("Failed to retrieve methodology notes")
        return []

    def specificity(n: dict[str, Any]) -> int:
        return (1 if n["scope_ticker"] else 0) + (1 if n["scope_persona"] else 0)

    notes.sort(key=lambda n: (-specificity(n), -(n["id"])))
    return notes[:limit]


def render_for_prompt(notes: list[dict[str, Any]]) -> str:
    """Format retrieved notes as a system-prompt section. Empty when none apply."""
    if not notes:
        return ""
    lines = [
        "",
        "Learned methodology (corrections from previous analyses — apply them):",
    ]
    for n in notes:
        scope_bits = [b for b in (n.get("scope_ticker"), n.get("scope_persona")) if b]
        scope = f" [{', '.join(scope_bits)}]" if scope_bits else ""
        lines.append(f"- {n['note']}{scope}")
    return "\n".join(lines)
