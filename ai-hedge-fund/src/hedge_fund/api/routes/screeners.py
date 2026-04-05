"""Screener endpoints — Yartseva Multibagger and future rules."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hedge_fund.screeners.yartseva import run_yartseva_for_ticker

router = APIRouter()

CONFIG_DIR = Path(__file__).resolve().parents[4] / "config"


class YartsevaRequest(BaseModel):
    tickers: list[str] | None = Field(
        default=None,
        description="Symbols to screen. If omitted, uses watchlist_group from config/watchlists.json.",
    )
    watchlist_group: str | None = Field(
        default="default",
        description="Watchlist key when tickers is empty.",
    )


def _load_watchlist(group: str) -> list[str]:
    path = CONFIG_DIR / "watchlists.json"
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="watchlists.json not found",
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get(group)
    if not isinstance(raw, list) or not raw:
        raise HTTPException(
            status_code=400,
            detail=f"watchlist group {group!r} is missing or empty",
        )
    return [str(x).strip().upper() for x in raw if str(x).strip()]


@router.post("/yartseva")
async def run_yartseva(req: YartsevaRequest):
    """
    Run Yartseva Multibagger Stage 1 filters + Stage 2 composite scoring.

    Uses yfinance (quarterly TTM sums) — verify figures against filings before trading.
    """
    if req.tickers:
        tickers = [t.strip().upper() for t in req.tickers if t.strip()]
    else:
        tickers = _load_watchlist(req.watchlist_group or "default")

    if not tickers:
        raise HTTPException(status_code=400, detail="no tickers to screen")

    results: list[dict] = []
    for t in tickers:
        results.append(await asyncio.to_thread(run_yartseva_for_ticker, t))

    def _sort_key(r: dict) -> tuple:
        c = r.get("composite")
        if c is None:
            return (1, 0.0)
        return (0, -float(c))

    results.sort(key=_sort_key)

    return {
        "macro_regime_note": (
            "Macro regime is portfolio-level: Fed stable/cutting = full weight; "
            "active hiking raise strong threshold to ~65+; aggressive hiking (>150bps) reduce exposure."
        ),
        "watchlist_group": req.watchlist_group if not req.tickers else None,
        "tickers": tickers,
        "count": len(results),
        "results": results,
    }
