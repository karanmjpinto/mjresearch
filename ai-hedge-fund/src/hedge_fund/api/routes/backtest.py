"""Rule-based backtest endpoints — strategy over historical price series."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from hedge_fund.data.frames import normalise_prices
from hedge_fund.data.service import get_data_service
from hedge_fund.quant.backtest import (
    STRATEGY_META,
    STRATEGY_REGISTRY,
    run_backtest,
)

logger = logging.getLogger(__name__)
router = APIRouter()
_ds = get_data_service()


@router.get("/strategies")
def list_strategies() -> dict[str, Any]:
    """List all available strategies with their default params and descriptions."""
    return {
        "strategies": [
            {
                "id": meta.id,
                "name": meta.name,
                "description": meta.description,
                "default_params": meta.default_params,
                "category": meta.category,
            }
            for meta in STRATEGY_META.values()
        ]
    }


@router.get("/{ticker}")
def run(
    ticker: str,
    strategy: str = Query(default="golden_cross"),
    days: int = Query(default=1095, ge=60, le=3650),
    fee_bps: int = Query(default=5, ge=0, le=100, description="Per-side fee in basis points"),
    rf_annual: float = Query(default=0.04, ge=0.0, le=0.15),
) -> dict[str, Any]:
    """Run a strategy backtest on historical prices for a ticker.

    The engine applies a one-bar lag on signals (no look-ahead), charges
    `fee_bps` on each position change, and returns the equity curve,
    metrics, and trade log.
    """
    ticker = ticker.upper().strip()
    if strategy not in STRATEGY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy '{strategy}'. See /api/backtest/strategies.",
        )

    try:
        df = _ds.get_price_history(ticker, days=days)
    except Exception as exc:
        logger.exception("Price fetch failed for %s", ticker)
        raise HTTPException(status_code=502, detail=f"Price fetch failed: {exc}") from exc

    # `normalise_prices` also absorbs the shapes the provider chain returns —
    # a frame, a list of records, or a {"data": [...]} envelope — so the route
    # does not have to know which one answered.
    df = normalise_prices(df)
    if df is None:
        raise HTTPException(status_code=404, detail=f"No usable price data for {ticker}")

    try:
        result = run_backtest(
            df=df,
            ticker=ticker,
            strategy_id=strategy,
            fee_pct=fee_bps / 10000.0,
            rf_annual=rf_annual,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return result.to_dict()
