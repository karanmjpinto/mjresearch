"""Portfolio optimization — build weights from a basket + (optional) AI convictions."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hedge_fund.data.batch import fetch_prices
from hedge_fund.data.frames import close_series
from hedge_fund.data.service import get_data_service
from hedge_fund.quant.portfolio import (
    METHOD_META,
    METHOD_REGISTRY,
    optimize_weights,
    portfolio_metrics,
)

logger = logging.getLogger(__name__)
router = APIRouter()
_ds = get_data_service()


class OptimizeRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=30)
    method: str = "hrp"
    days: int = Field(default=730, ge=60, le=3650)
    rf_annual: float = Field(default=0.04, ge=0.0, le=0.15)
    convictions: dict[str, float] | None = Field(
        default=None,
        description="Optional {ticker: 0..100} conviction map from AI committee.",
    )


@router.get("/methods")
def list_methods() -> dict[str, Any]:
    return {
        "methods": [
            {
                "id": m.id,
                "name": m.name,
                "description": m.description,
                "uses_conviction": m.uses_conviction,
                "uses_returns": m.uses_returns,
                "category": m.category,
            }
            for m in METHOD_META.values()
        ]
    }


@router.post("")
def optimize(req: OptimizeRequest) -> dict[str, Any]:
    if req.method not in METHOD_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown method '{req.method}'. See /api/optimize/methods.",
        )

    tickers = [t.upper().strip() for t in req.tickers if t.strip()]
    tickers = list(dict.fromkeys(tickers))  # dedup, preserve order
    if len(tickers) < 2:
        raise HTTPException(400, "Need at least 2 tickers.")

    # In parallel, not one after another: a provider call is about a second of
    # network wait, so an eight-name basket took eleven seconds serially and
    # takes under two this way. A name whose fetch fails is simply absent.
    frames = fetch_prices(tickers, days=req.days, data_service=_ds)

    # calendar_days because these series are joined on date below. The
    # providers disagree about what a date is — yfinance a tz-aware exchange
    # stamp, OpenBB a naive one, some paths a 09:30 session time — and
    # unfloored a six-name basket either raises on the concat or joins to an
    # empty frame that reads as "these names never traded together".
    closes: dict[str, pd.Series] = {}
    for t in tickers:
        close = close_series(frames.get(t), min_points=20, calendar_days=True)
        if close is not None:
            closes[t] = close

    if len(closes) < 2:
        raise HTTPException(
            422,
            f"Need price history for at least 2 tickers; got {len(closes)} of {len(tickers)}.",
        )

    # Align all close series on common dates
    prices = pd.concat(closes, axis=1).dropna(how="any")
    if len(prices) < 20:
        raise HTTPException(422, f"Only {len(prices)} common bars across tickers — too few.")

    returns = prices.pct_change().dropna()

    weights = optimize_weights(req.method, returns, req.convictions)

    # Compute portfolio metrics on those weights
    metrics = portfolio_metrics(weights, returns, rf_annual=req.rf_annual)

    # Also compute equal-weight metrics for comparison
    n = len(returns.columns)
    eq_weights = np.full(n, 1.0 / n)
    eq_metrics = portfolio_metrics(eq_weights, returns, rf_annual=req.rf_annual)

    # Per-asset detail
    assets = []
    for i, t in enumerate(returns.columns):
        asset_vol = float(returns[t].std() * np.sqrt(252))
        asset_ret = float(returns[t].mean() * 252)
        conviction = (
            float(req.convictions.get(t)) if req.convictions and t in req.convictions else None
        )
        assets.append(
            {
                "ticker": t,
                "weight": round(float(weights[i]), 6),
                "expected_return": round(asset_ret, 6),
                "volatility": round(asset_vol, 6),
                "conviction": conviction,
            }
        )

    meta = METHOD_META[req.method]

    return {
        "method_id": req.method,
        "method_name": meta.name,
        "method_description": meta.description,
        "start_date": prices.index[0].strftime("%Y-%m-%d")
        if hasattr(prices.index[0], "strftime")
        else str(prices.index[0]),
        "end_date": prices.index[-1].strftime("%Y-%m-%d")
        if hasattr(prices.index[-1], "strftime")
        else str(prices.index[-1]),
        "n_bars": int(len(returns)),
        "assets": assets,
        "metrics": metrics,
        "equal_weight_metrics": eq_metrics,
        "excluded_tickers": [t for t in tickers if t not in closes],
    }
