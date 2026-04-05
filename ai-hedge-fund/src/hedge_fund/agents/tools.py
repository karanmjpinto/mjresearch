"""Structured tool functions for AI agents — delegate to DataService (OpenBB + fallbacks).

Use these from LLM tool-calling loops or a future MCP server so market data stays
behind one facade instead of calling yfinance or OpenBB directly.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hedge_fund.data.service import get_data_service
from hedge_fund.nlp.news_sentiment import enrich_news_with_sentiment


def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    out = df.reset_index()
    out.columns = [str(c) for c in out.columns]
    for col in out.columns:
        if hasattr(out[col], "dt"):
            out[col] = out[col].astype(str)
    return out.to_dict(orient="records")


def tool_price_history(ticker: str, days: int = 365) -> dict[str, Any]:
    """OHLCV history for a symbol."""
    ds = get_data_service()
    sym = ticker.upper().strip()
    df = ds.get_price_history(sym, days=days)
    if df.empty:
        return {"ok": False, "ticker": sym, "error": "no data", "data": []}
    return {"ok": True, "ticker": sym, "count": len(df), "data": _df_to_records(df)}


def tool_fundamentals(ticker: str) -> dict[str, Any]:
    """Key fundamental metrics."""
    ds = get_data_service()
    sym = ticker.upper().strip()
    result = ds.get_fundamentals(sym)
    if "error" in result:
        return {"ok": False, "ticker": sym, "error": result.get("error"), "data": {}}
    return {"ok": True, "ticker": sym, "data": result}


def tool_technicals(ticker: str) -> dict[str, Any]:
    """RSI, MACD, Bollinger, SMAs, ATR."""
    ds = get_data_service()
    sym = ticker.upper().strip()
    result = ds.get_technical_indicators(sym)
    if "error" in result:
        return {"ok": False, "ticker": sym, "error": result.get("error"), "data": {}}
    return {"ok": True, "ticker": sym, "data": result}


def tool_news(query: str, limit: int = 10) -> dict[str, Any]:
    """News articles for a ticker or search string."""
    ds = get_data_service()
    articles = ds.get_news(query, limit=limit)
    return {"ok": True, "query": query, "count": len(articles), "articles": articles}


def tool_research_snapshot(ticker: str) -> dict[str, Any]:
    """Aggregated research payload (price summary, fundamentals, technicals, news)."""
    ds = get_data_service()
    sym = ticker.upper().strip()
    fundamentals = ds.get_fundamentals(sym)
    technicals = ds.get_technical_indicators(sym)
    df = ds.get_price_history(sym, days=30)
    price_summary: dict[str, Any] = {}
    if not df.empty:
        close = df["close"]
        price_summary = {
            "current": float(close.iloc[-1]),
            "change_30d_pct": round((float(close.iloc[-1]) / float(close.iloc[0]) - 1) * 100, 2),
            "high_30d": float(close.max()),
            "low_30d": float(close.min()),
        }
    news = ds.get_news(sym, limit=5)
    news_list = [
        {"title": n.get("title", ""), "date": str(n.get("date", n.get("published", "")))}
        for n in news
    ]
    enriched, ns_meta = enrich_news_with_sentiment(news_list)
    return {
        "ok": True,
        "ticker": sym,
        "price": price_summary,
        "fundamentals": fundamentals,
        "technicals": technicals,
        "news": enriched,
        "news_sentiment": ns_meta,
    }


# Registry for introspection (e.g. MCP or future agent setup)
AGENT_TOOLS: dict[str, Any] = {
    "price_history": tool_price_history,
    "fundamentals": tool_fundamentals,
    "technicals": tool_technicals,
    "news": tool_news,
    "research_snapshot": tool_research_snapshot,
}
