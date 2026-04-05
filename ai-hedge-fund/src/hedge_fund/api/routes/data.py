"""Data endpoints — price, fundamentals, technicals, macro, news + 13 new categories."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from hedge_fund.data.service import get_data_service

router = APIRouter()
_ds = get_data_service()

CONFIG_DIR = Path(__file__).resolve().parents[4] / "config"


# ------------------------------------------------------------------
# Original 5 endpoints (backward compatible)
# ------------------------------------------------------------------


@router.get("/price/{ticker}")
async def get_price(ticker: str, days: int = Query(365, ge=1, le=3650)):
    """OHLCV price history."""
    df = _ds.get_price_history(ticker, days=days)
    if df.empty:
        raise HTTPException(404, f"No price data for {ticker}")
    df = df.reset_index()
    df.columns = [str(c) for c in df.columns]
    for col in df.columns:
        if hasattr(df[col], "dt"):
            df[col] = df[col].astype(str)
    return {"ticker": ticker, "count": len(df), "data": df.to_dict(orient="records")}


@router.get("/fundamentals/{ticker}")
async def get_fundamentals(ticker: str):
    """Key fundamental metrics."""
    result = _ds.get_fundamentals(ticker)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/technicals/{ticker}")
async def get_technicals(ticker: str):
    """RSI, MACD, SMA, Bollinger Bands, ATR and trend."""
    result = _ds.get_technical_indicators(ticker)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/macro/{series}")
async def get_macro(series: str, days: int = Query(1825, ge=30, le=7300)):
    """FRED macro time series."""
    df = _ds.get_macro_data(series, days=days)
    if df.empty:
        raise HTTPException(404, f"No macro data for {series}")
    df = df.reset_index()
    df.columns = [str(c) for c in df.columns]
    for col in df.columns:
        if hasattr(df[col], "dt"):
            df[col] = df[col].astype(str)
    return {"series": series, "count": len(df), "data": df.to_dict(orient="records")}


@router.get("/news")
async def get_news(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    """News search."""
    results = _ds.get_news(q, limit=limit)
    return {"query": q, "count": len(results), "articles": results}


# ------------------------------------------------------------------
# New endpoints — 13 additional data categories
# ------------------------------------------------------------------


@router.get("/esg/{ticker}")
async def get_esg(ticker: str):
    """ESG scores (requires Finnhub API key)."""
    result = _ds.get_esg(ticker)
    if result is None:
        raise HTTPException(404, f"No ESG data for {ticker}")
    return _serialize(result)


@router.get("/insider/{ticker}")
async def get_insider(ticker: str):
    """Insider transactions."""
    result = _ds.get_insider(ticker)
    if result is None:
        raise HTTPException(404, f"No insider data for {ticker}")
    return {"ticker": ticker, "transactions": _serialize(result)}


@router.get("/institutional/{ticker}")
async def get_institutional(ticker: str):
    """Institutional holders."""
    result = _ds.get_institutional(ticker)
    if result is None:
        raise HTTPException(404, f"No institutional data for {ticker}")
    return {"ticker": ticker, "holders": _serialize(result)}


@router.get("/earnings/{ticker}")
async def get_earnings(ticker: str):
    """Earnings dates, history, estimates."""
    result = _ds.get_earnings(ticker)
    if result is None:
        raise HTTPException(404, f"No earnings data for {ticker}")
    return _serialize(result)


@router.get("/analyst/{ticker}")
async def get_analyst(ticker: str):
    """Analyst ratings and price targets."""
    result = _ds.get_analyst(ticker)
    if result is None:
        raise HTTPException(404, f"No analyst data for {ticker}")
    return _serialize(result)


@router.get("/sentiment/{ticker}")
async def get_sentiment(ticker: str):
    """News sentiment scores (requires Finnhub API key)."""
    result = _ds.get_sentiment(ticker)
    if result is None:
        raise HTTPException(404, f"No sentiment data for {ticker}")
    return _serialize(result)


@router.get("/sector-performance")
async def get_sector_performance():
    """Real-time sector performance rankings."""
    result = _ds.get_sector_performance()
    if result is None:
        return {
            "realtime": [],
            "one_day": [],
            "five_day": [],
            "one_month": [],
            "three_month": [],
            "ytd": [],
            "one_year": [],
            "source": "unavailable",
        }
    return _serialize(result)


@router.get("/fama-french")
async def get_fama_french():
    """Fama-French 5-factor data."""
    result = _ds.get_fama_french()
    if result is None:
        raise HTTPException(404, "No Fama-French data available")
    return _serialize(result)


@router.get("/options/{ticker}")
async def get_options(ticker: str):
    """Options chain data."""
    result = _ds.get_options(ticker)
    if result is None:
        raise HTTPException(404, f"No options data for {ticker}")
    return _serialize(result)


@router.get("/filings/{ticker}")
async def get_filings(ticker: str):
    """SEC filings (requires Finnhub API key)."""
    result = _ds.get_filings(ticker)
    if result is None:
        raise HTTPException(404, f"No filings data for {ticker}")
    return {"ticker": ticker, "filings": _serialize(result)}


@router.get("/congressional/{ticker}")
async def get_congressional(ticker: str):
    """Congressional trades (requires Finnhub API key)."""
    result = _ds.get_congressional(ticker)
    if result is None:
        raise HTTPException(404, f"No congressional trade data for {ticker}")
    return {"ticker": ticker, "trades": _serialize(result)}


@router.get("/peers/{ticker}")
async def get_peers(ticker: str):
    """Peer comparison data."""
    result = _ds.get_peers(ticker)
    if result is None:
        raise HTTPException(404, f"No peer data for {ticker}")
    return _serialize(result)


@router.get("/providers/status")
async def get_provider_status():
    """Status of all registered data providers."""
    return {"providers": _ds.get_provider_status()}


@router.get("/watchlists")
async def get_watchlists():
    """Named ticker lists for the research dashboard (edit config/watchlists.json)."""
    path = CONFIG_DIR / "watchlists.json"
    if not path.exists():
        raise HTTPException(404, "watchlists.json not found")
    with open(path) as f:
        return json.load(f)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _serialize(obj):
    """Convert Pydantic models or lists of models to dicts."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in obj
        ]
    return obj
