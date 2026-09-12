"""Your own notes as a stage in the flow.

The company's name, sector and industry come from the data layer rather than
the query string, so the match is against what the filing says the company is
— not against whatever the caller happened to type.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from hedge_fund.data.service import get_data_service
from hedge_fund.knowledge.lens import build_lens
from hedge_fund.knowledge.match import coverage
from hedge_fund.knowledge.vault import build_index, vault_root

logger = logging.getLogger(__name__)
router = APIRouter()
_ds = get_data_service()

#: How long to wait for the filesystem before giving up on the vault.
#: Walking a few thousand files takes well under a second; anything past this
#: is a directory that is not going to answer — an unmounted drive, a network
#: share that is gone, or a sandboxed process waiting on a permission grant
#: that has no one to approve it.
VAULT_TIMEOUT_S = 8.0


async def _off_loop(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a blocking vault read off the event loop, and never wait forever.

    Reading the vault is synchronous file I/O. Awaiting it directly on the
    event loop means one slow directory stops *every* request the process is
    serving, not just this one — which is exactly what happened: a vault that
    never answered took the whole API down with it while the rest of the app
    was perfectly healthy. The threadpool contains the blockage to one worker,
    and the timeout turns "hangs forever" into an answer the caller can render.
    """
    return await asyncio.wait_for(
        run_in_threadpool(lambda: fn(*args, **kwargs)), timeout=VAULT_TIMEOUT_S
    )


@router.get("/status")
async def status() -> dict[str, Any]:
    """Whether a vault is connected, and how much is in it."""
    root = await _off_loop(vault_root)
    if root is None:
        return {"configured": False, "notes": 0}
    try:
        index = await _off_loop(build_index)
    except TimeoutError:
        logger.warning("vault did not respond within %.0fs", VAULT_TIMEOUT_S)
        return {"configured": True, "notes": 0, "unreadable": True}
    return {
        "configured": True,
        "notes": len(index.notes) if index else 0,
        "built_at": index.built_at if index else "",
    }


@router.get("/lens/{ticker}")
async def lens(ticker: str) -> dict[str, Any]:
    """What you have already written that touches this company."""
    t = ticker.strip().upper()

    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    try:
        profile = _ds.get_fundamentals(t) or {}
        if not profile.get("error"):
            name = profile.get("name")
            sector = profile.get("sector")
            industry = profile.get("industry")
    except Exception as exc:  # noqa: BLE001 — an absent profile must not lose the stage
        # Without a profile the ticker still matches; only the theme layer
        # narrows, so degrade rather than fail.
        logger.info("no profile for %s (%s); matching on ticker alone", t, exc)

    try:
        out = await _off_loop(build_lens, t, name=name, sector=sector, industry=industry)
    except TimeoutError:
        logger.warning(
            "vault did not respond within %.0fs; serving %s without it", VAULT_TIMEOUT_S, t
        )
        out = {
            "ticker": t,
            "configured": True,
            "unreadable": True,
            "finding": (
                "Your notes folder did not respond. If it is on an external or network drive, "
                "reconnect it; if this process cannot see your home folder, grant it access."
            ),
            "coverage": coverage([]),
            "company": [],
            "themes": [],
            "frameworks": [],
        }

    out["subject"] = {"name": name, "sector": sector, "industry": industry}
    return out
