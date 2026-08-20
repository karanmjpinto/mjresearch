"""Screener endpoints — Yartseva Multibagger and future rules."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hedge_fund.data.universes import list_universe_meta, load_universe
from hedge_fund.screeners.acquisition_compounder import run_acquisition_compounder_for_ticker
from hedge_fund.screeners.yartseva import run_yartseva_for_ticker

router = APIRouter()
logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[4] / "config"


class ScreenerRunRequest(BaseModel):
    tickers: list[str] | None = Field(
        default=None,
        description="Symbols to screen. If set, overrides universe and watchlist_group.",
    )
    watchlist_group: str | None = Field(
        default="default",
        description="Watchlist key from config/watchlists.json when tickers and universe are empty.",
    )
    universe: str | None = Field(
        default=None,
        description="Index universe id: sp500, nasdaq100, dow, russell2000 (see GET /screeners/universes).",
    )
    max_symbols: int = Field(
        default=500,
        ge=1,
        le=5000,
        description="Cap universe size after loading (large indices are slow per ticker).",
    )


# Backward-compatible alias
YartsevaRequest = ScreenerRunRequest


def _resolve_screener_tickers(
    req: ScreenerRunRequest,
) -> tuple[list[str], str | None, int | None, bool]:
    """Returns (tickers, universe_id, universe_total, truncated)."""
    universe_id: str | None = None
    universe_total: int | None = None
    truncated = False

    if req.tickers:
        return (
            [t.strip().upper() for t in req.tickers if t.strip()],
            None,
            None,
            False,
        )
    if req.universe and req.universe.strip():
        universe_id = req.universe.strip().lower()
        try:
            full = load_universe(universe_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.warning("universe load failed: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"failed to load universe {universe_id!r}: {e}",
            ) from e
        universe_total = len(full)
        tickers = full[: req.max_symbols]
        truncated = universe_total > len(tickers)
        return tickers, universe_id, universe_total, truncated

    tickers = _load_watchlist(req.watchlist_group or "default")
    return tickers, None, None, False


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


@router.get("/universes")
async def get_universes():
    """Index / ETF proxy universes available for screeners."""
    return {"universes": list_universe_meta()}


@router.post("/yartseva")
async def run_yartseva(req: ScreenerRunRequest):
    """
    Run Yartseva Multibagger Stage 1 filters + Stage 2 composite scoring.

    Uses yfinance (quarterly TTM sums) — verify figures against filings before trading.
    """
    tickers, universe_id, universe_total, truncated = _resolve_screener_tickers(req)

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
        "watchlist_group": req.watchlist_group if not req.tickers and not universe_id else None,
        "universe": universe_id,
        "universe_total": universe_total,
        "universe_truncated": truncated,
        "max_symbols": req.max_symbols if universe_id else None,
        "tickers": tickers,
        "count": len(results),
        "results": results,
    }


@router.post("/acquisition-compounder")
async def run_acquisition_compounder(req: ScreenerRunRequest):
    """
    Acquisition / bolt-on compounder: hard filters (growth, ROIC, FCF conversion, leverage,
    margins, dilution) + optional quality tier + 9-factor score (/45). Data is yfinance;
    organic growth uses revenue YoY / span CAGR proxies — verify in filings.
    """
    tickers, universe_id, universe_total, truncated = _resolve_screener_tickers(req)

    if not tickers:
        raise HTTPException(status_code=400, detail="no tickers to screen")

    results: list[dict] = []
    for t in tickers:
        results.append(await asyncio.to_thread(run_acquisition_compounder_for_ticker, t))

    def _sort_key(r: dict) -> tuple:
        ts = r.get("total_score")
        if ts is None:
            return (1, 0.0)
        return (0, -float(ts))

    results.sort(key=_sort_key)

    return {
        "methodology_note": (
            "Growth metrics use available annual FY columns or TTM series; when Yahoo returns "
            "short history, span-CAGR and revenueGrowth are approximations. Organic revenue "
            "uses YoY revenue growth as a proxy. Goodwill impairments may be incomplete. "
            "Not investment advice."
        ),
        "watchlist_group": req.watchlist_group if not req.tickers and not universe_id else None,
        "universe": universe_id,
        "universe_total": universe_total,
        "universe_truncated": truncated,
        "max_symbols": req.max_symbols if universe_id else None,
        "tickers": tickers,
        "count": len(results),
        "results": results,
    }
