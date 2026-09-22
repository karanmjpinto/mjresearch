"""JKP factor returns, and one company's position on them.

All three endpoints are computed: no model is called. The returns are the
published JKP series from a committed file, so they answer offline; the profile
reads the screen caches, and only reaches a data provider for a ticker that is
in none of them.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException

from hedge_fund.agents.guardrails import GuardrailError, sanitize_ticker
from hedge_fund.factors import exposure, jkp

router = APIRouter()
logger = logging.getLogger(__name__)

REFRESH = "uv run python scripts/refresh_jkp.py"


def _missing() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=f"JKP factor data is not on this server. Rebuild it with: {REFRESH}",
    )


@router.get("/themes")
async def themes() -> dict[str, Any]:
    try:
        return jkp.theme_rows()
    except jkp.FactorDataMissing as exc:
        raise _missing() from exc


@router.get("/themes/{theme_id}")
async def theme_factors(theme_id: str) -> dict[str, Any]:
    try:
        got = jkp.factor_rows(theme_id)
    except jkp.FactorDataMissing as exc:
        raise _missing() from exc
    if got is None:
        raise HTTPException(status_code=404, detail=f"no JKP theme {theme_id!r}")
    return got


def _fetch_live(ticker: str) -> dict[str, Any]:
    """The fields two screens fetch, for a name no cache holds.

    The same fetchers the screens use, so a live name is measured exactly the
    way its peers were rather than through a different provider's definitions.
    """
    from hedge_fund.screeners.bolton_contrarian import fetch_bolton_snapshot
    from hedge_fund.screeners.yartseva import fetch_yartseva_snapshot

    flat: dict[str, Any] = {}
    for fetch in (fetch_bolton_snapshot, fetch_yartseva_snapshot):
        try:
            snap = asdict(fetch(ticker))
        except Exception as exc:  # noqa: BLE001 — one fetcher failing leaves the other
            logger.warning("%s: live factor fields failed (%s)", ticker, exc)
            continue
        if snap.get("error"):
            continue
        for k, v in snap.items():
            if v is not None:
                flat.setdefault(k, v)
    return flat


@router.get("/profile/{ticker}")
async def profile(ticker: str, live: bool = True) -> dict[str, Any]:
    try:
        symbol = sanitize_ticker(ticker)
    except GuardrailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        jkp.load()
    except jkp.FactorDataMissing as exc:
        raise _missing() from exc

    universe, sources = await asyncio.to_thread(exposure.reference_universe)
    target = None
    if symbol not in universe and live:
        target = await asyncio.to_thread(_fetch_live, symbol)
    return exposure.profile(symbol, target=target, universe=universe, sources=sources)
