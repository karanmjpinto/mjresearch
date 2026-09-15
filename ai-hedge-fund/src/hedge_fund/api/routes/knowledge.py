"""Your own notes as a stage in the flow.

The company's name, sector and industry come from the data layer rather than
the query string, so the match is against what the filing says the company is
— not against whatever the caller happened to type.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from hedge_fund.data.service import get_data_service
from hedge_fund.knowledge.apply import apply_framework
from hedge_fund.knowledge.lens import build_lens, framework_titles
from hedge_fund.knowledge.match import coverage
from hedge_fund.knowledge.vault import build_index, vault_root
from hedge_fund.knowledge.writeback import WriteBackError, render, write

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


# ------------------------------------------------------------------
# Stage 04, phase 3 — frameworks run rather than listed, and a page back
# ------------------------------------------------------------------


def _company_metrics(ticker: str) -> dict[str, Any]:
    """The figures a checklist line might be about, under stable keys.

    Taken from fundamentals rather than recomputed, so a line checked here and
    the same number shown on stage 02 cannot disagree.
    """
    f = _ds.get_fundamentals(ticker) or {}
    if f.get("error"):
        return {}
    return {k: v for k, v in f.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def _framework_bodies(index: Any, titles: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """(title, path, body) for each framework note, read from disk."""
    root = vault_root()
    if root is None:
        return []
    wanted = {t.strip().lower() for t in titles}
    out: list[tuple[str, str, str]] = []
    for note in getattr(index, "notes", []):
        if note.title.strip().lower() not in wanted:
            continue
        try:
            body = (root / note.path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("framework %s unreadable (%s)", note.path, exc)
            continue
        out.append((note.title, note.path, body))
    return out


@router.get("/frameworks/{ticker}")
async def frameworks_applied(ticker: str, limit: int = 6) -> dict[str, Any]:
    """Each of your frameworks with this company's numbers beside every line."""
    t = ticker.strip().upper()

    if vault_root() is None:
        return {
            "ticker": t,
            "configured": False,
            "frameworks": [],
            "finding": (
                "No vault is connected. Set VAULT_PATH to your Obsidian folder and your "
                "own checklists will be run against this company here."
            ),
        }

    try:
        index = await _off_loop(build_index)
    except TimeoutError:
        return {
            "ticker": t,
            "configured": True,
            "unreadable": True,
            "frameworks": [],
            "finding": "The notes folder did not respond in time.",
        }

    if index is None or not index.notes:
        return {
            "ticker": t,
            "configured": True,
            "frameworks": [],
            "finding": "The vault is connected but empty.",
        }

    titles = framework_titles(index)
    bodies = await _off_loop(_framework_bodies, index, titles)
    if not bodies:
        return {
            "ticker": t,
            "configured": True,
            "frameworks": [],
            "finding": (
                "No framework notes found. Name them in config/vault.json, or put them in "
                "a folder listed there, and they will be run against every company."
            ),
        }

    metrics = await run_in_threadpool(_company_metrics, t)
    applied = [
        apply_framework(title, path, body, metrics).as_dict()
        for title, path, body in bodies[: max(1, limit)]
    ]
    # Most checkable first: a framework this data can actually answer is worth
    # more of the reader's attention than one that comes back all judgment.
    applied.sort(key=lambda a: -a["answerable"])

    checkable = sum(a["answerable"] for a in applied)
    return {
        "ticker": t,
        "configured": True,
        "frameworks": applied,
        "metrics_available": len(metrics),
        "finding": (
            f"{len(applied)} of your frameworks run against {t}, with {checkable} "
            "lines that can be checked against reported figures."
            if checkable
            else (
                f"{len(applied)} frameworks matched, but none of their lines can be checked "
                "against the figures on hand — they ask for judgments."
            )
        ),
    }


def _one_pager_sections(ticker: str) -> tuple[dict[str, str], list[str], str | None]:
    """What goes in the note: the reasoning, not a dump of every field."""
    f = _ds.get_fundamentals(ticker) or {}
    name = f.get("name") if not f.get("error") else None

    price = f.get("current_price")
    sector = f.get("sector")
    industry = f.get("industry")

    facts = [
        f"- Sector: {sector or 'not reported'}" + (f" / {industry}" if industry else ""),
        f"- Price when this page was written: {price if price is not None else 'not reported'}",
        f"- Market capitalisation: {f.get('market_cap') or 'not reported'}",
    ]

    sections = {
        "The question": (
            f"What would have to be true for {ticker} to be worth more than "
            f"{price if price is not None else 'the current price'}?"
        ),
        "What the data says": "\n".join(facts),
        "The four drivers": (
            "- Revenue growth:\n- Target operating margin:\n"
            "- Sales to capital:\n- Cost of capital:\n\n"
            "_Filled in on stage 05; copy the figures you settled on._"
        ),
        "Where I could be wrong": (
            "- \n\n_The weakest leg of the argument, stated before the position is taken._"
        ),
        "The decision": "- Call:\n- Size:\n- Review on:",
    }
    return sections, [], name


@router.get("/one-pager/{ticker}")
async def one_pager_preview(ticker: str) -> dict[str, Any]:
    """The note that would be written, without writing it."""
    t = ticker.strip().upper()
    try:
        index = await _off_loop(build_index)
    except TimeoutError:
        index = None

    sections, links, name = await run_in_threadpool(_one_pager_sections, t)

    # Whatever already matched becomes the link list, so the page lands joined
    # to the graph instead of as an orphan.
    try:
        lens = await _off_loop(build_lens, t, name=name)
        links = [
            m["title"]
            for kind in ("company", "themes", "frameworks")
            for m in lens.get(kind, [])
            if m.get("title")
        ][:12]
    except (TimeoutError, Exception) as exc:  # noqa: BLE001 - preview must not fail
        logger.warning("lens unavailable for one-pager links (%s)", exc)

    try:
        page = await run_in_threadpool(
            render, t, name=name, sections=sections, links=links, index=index
        )
    except WriteBackError as exc:
        return {"ticker": t, "available": False, "reason": str(exc)}

    return {"ticker": t, "available": True, **page.as_dict()}


@router.post("/one-pager/{ticker}")
async def one_pager_write(ticker: str) -> dict[str, Any]:
    """Write the note into the vault. Refuses to replace an existing page."""
    t = ticker.strip().upper()
    try:
        index = await _off_loop(build_index)
    except TimeoutError:
        index = None

    sections, links, name = await run_in_threadpool(_one_pager_sections, t)
    try:
        lens = await _off_loop(build_lens, t, name=name)
        links = [
            m["title"]
            for kind in ("company", "themes", "frameworks")
            for m in lens.get(kind, [])
            if m.get("title")
        ][:12]
    except (TimeoutError, Exception) as exc:  # noqa: BLE001
        logger.warning("lens unavailable for one-pager links (%s)", exc)

    try:
        page = await run_in_threadpool(
            render, t, name=name, sections=sections, links=links, index=index
        )
        result = await run_in_threadpool(write, page)
    except WriteBackError as exc:
        # 409, not 500: the request was understood and deliberately refused.
        raise HTTPException(409, str(exc)) from exc

    return {"ticker": t, **result}
