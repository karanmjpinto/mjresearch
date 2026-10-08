"""The growth/inflation map, and where one company sits on it.

Everything but the company is computed from committed files, so the map draws
offline. A ticker is the only thing that reaches a data provider, and it needs
a long price history — a decade of overlapping year-long windows is the floor
below which the two correlations stop meaning anything, so a recent listing is
told it is too young rather than given a point.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException

from hedge_fund.agents.guardrails import GuardrailError, sanitize_ticker
from hedge_fund.data.frames import close_series
from hedge_fund.macro import news, sensitivity

router = APIRouter()
logger = logging.getLogger(__name__)

#: Enough calendar to clear `news.MIN_QUARTERS` windows with room for the
#: months a provider drops, plus the eleventh year the first window needs.
TICKER_DAYS = 365 * 22


def _missing() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=f"Macro news data is not on this server. Rebuild it with: {news.REFRESH}",
    )


@router.get("/map")
async def macro_map() -> dict[str, Any]:
    try:
        context = news.context()
    except news.MacroDataMissing as exc:
        raise _missing() from exc
    points = await asyncio.to_thread(
        lambda: sensitivity.reference_points() + sensitivity.factor_points()
    )
    return {"context": context, "points": points}


def _monthly_returns(ticker: str) -> tuple[list[str], list[float]]:
    """Month labels and simple returns from the provider chain's monthly closes.

    Thirteen closes, because twelve returns is the least that places a company
    on the quarterly map. An empty pair means "not enough history", which this
    route answers with a 404 rather than a fault.
    """
    from hedge_fund.data.service import get_data_service

    frame = get_data_service().get_price_history(ticker, days=TICKER_DAYS, interval="1mo")
    closes = close_series(frame, min_points=13)
    if closes is None:
        return [], []

    index = pd.PeriodIndex(closes.index, freq="M")
    changes = closes.pct_change().iloc[1:]
    return [str(p) for p in index[1:]], [float(v) for v in changes]


@router.get("/map/{ticker}")
async def macro_point(ticker: str) -> dict[str, Any]:
    try:
        symbol = sanitize_ticker(ticker)
    except GuardrailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        news.load()
    except news.MacroDataMissing as exc:
        raise _missing() from exc

    months, returns = await asyncio.to_thread(_monthly_returns, symbol)
    if not months:
        raise HTTPException(status_code=404, detail=f"no monthly price history for {symbol}")

    quarterly = sensitivity.from_monthly(months, returns)
    try:
        point = sensitivity.sensitivity(quarterly)
    except sensitivity.NotEnoughHistory as exc:
        # Not an error in the provider or the request: this company has simply
        # not existed long enough to be placed, and saying so is the answer.
        return {
            "ticker": symbol,
            "point": None,
            "reason": str(exc),
            "months_available": len(months),
        }

    point.update(
        label=symbol,
        kind="company",
        id=f"company_{symbol}",
        note="This company's own monthly total return, over whatever history the provider holds.",
    )
    return {"ticker": symbol, "point": point, "reason": None, "months_available": len(months)}
