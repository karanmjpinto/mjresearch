"""The way in when you do not have a ticker yet.

Two lists, kept apart in the response rather than merged into one ranking. A
curated constraint with sourced measurements and a subject pulled out of your
own notes are not the same kind of claim, and interleaving them by score would
be the one move that makes the honest half look like the confident half.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from hedge_fund.constraints.catalogue import (
    SYSTEMS,
    CatalogueError,
    by_id,
    live,
    rejected,
)
from hedge_fund.constraints.derive import derive_candidates
from hedge_fund.knowledge.vault import build_index, vault_root

logger = logging.getLogger(__name__)
router = APIRouter()

#: Same guard as the knowledge routes, for the same reason: the vault walk is
#: blocking file I/O, and a directory that never answers must not be able to
#: stop every other request the process is serving.
VAULT_TIMEOUT_S = 8.0


async def _derived() -> tuple[list[dict[str, Any]], str | None]:
    """Vault-derived candidates, plus why the list is empty when it is."""
    if vault_root() is None:
        return [], "No vault connected, so there is nothing of yours to read."
    try:
        index = await asyncio.wait_for(run_in_threadpool(build_index), timeout=VAULT_TIMEOUT_S)
    except TimeoutError:
        logger.warning("vault did not respond within %.0fs", VAULT_TIMEOUT_S)
        return [], "Your notes folder did not respond in time."

    if index is None or not index.notes:
        return [], "The vault is connected but empty."

    found = await run_in_threadpool(derive_candidates, index)
    if not found:
        return [], (
            "Nothing in your notes reads as a constraint yet — no subject has "
            "several notes about something being unavailable."
        )
    return [d.as_dict() for d in found], None


@router.get("")
@router.get("/")
async def list_constraints(
    system: str | None = Query(None, description="intelligence | power | motion"),
) -> dict[str, Any]:
    """Both maps, side by side and labelled."""
    if system is not None and system.strip().lower() not in SYSTEMS:
        raise HTTPException(400, f"unknown system {system!r}; expected one of {', '.join(SYSTEMS)}")

    try:
        curated = list(live())
        dismissed = list(rejected())
    except CatalogueError as exc:
        # A broken map is worth surfacing rather than silently showing nothing:
        # the curated file is hand-edited, so a typo is a likely cause.
        logger.error("curated constraint map unusable: %s", exc)
        raise HTTPException(500, f"the curated constraint map is unusable: {exc}") from exc

    if system:
        wanted = system.strip().lower()
        curated = [c for c in curated if c.system == wanted]
        dismissed = [c for c in dismissed if c.system == wanted]

    derived, derived_note = await _derived()

    return {
        "systems": list(SYSTEMS),
        "filtered_to": system.strip().lower() if system else None,
        "curated": {
            "constraints": [c.as_dict(with_names=False) for c in curated],
            "note": None
            if curated
            else "The curated constraint map is not installed (config/constraints.json).",
        },
        "from_your_notes": {"constraints": derived, "note": derived_note},
        # Negative results, kept deliberately. Knowing a chokepoint was checked
        # and did not hold is what stops the same idea being re-researched from
        # scratch every quarter.
        "checked_and_rejected": {
            "constraints": [c.as_dict(with_names=False) for c in dismissed],
            "note": "Looked at, and the evidence said no. Kept so the idea does not come back unexamined.",
        },
    }


@router.get("/{constraint_id}")
async def constraint_detail(constraint_id: str) -> dict[str, Any]:
    """One curated constraint: its validation, its evidence, and the names on it."""
    if constraint_id.startswith("vault:"):
        # Derived candidates have no detail page of their own — everything
        # known about them is already in the list, because nothing about them
        # has been validated. Saying so beats a page of empty panels.
        raise HTTPException(
            404,
            "That candidate came from your notes and has no validated detail yet. "
            "Answer its three questions and it becomes a curated entry.",
        )

    found = by_id(constraint_id)
    if found is None:
        raise HTTPException(404, f"no constraint {constraint_id!r}")
    return found.as_dict()


@router.get("/{constraint_id}/candidates")
async def constraint_candidates(constraint_id: str) -> dict[str, Any]:
    """The listed names on this chokepoint, purest exposure first.

    Ranked by how concentrated the exposure is, not by any view on the
    companies themselves — a pure play transmits the squeeze and a conglomerate
    dilutes it into noise, whatever either is worth. What each name is worth is
    the next four stages' job, which is why every row carries its ticker.
    """
    found = by_id(constraint_id)
    if found is None:
        raise HTTPException(404, f"no constraint {constraint_id!r}")

    validation = found.as_dict(with_names=False)["validation"]
    return {
        "constraint": {"id": found.id, "name": found.name, "system": found.system},
        # Repeated deliberately: a shortlist read without the validation beside
        # it is just a list of tickers, which is what this tool exists not to be.
        "validation": validation,
        "ranked_by": "how concentrated each company's exposure to this chokepoint is",
        "names": [n.as_dict() for n in found.ranked_names()],
    }
