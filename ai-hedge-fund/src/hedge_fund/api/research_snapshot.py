"""Shared research snapshot builder for /research/check and /simulation/backtest."""

from __future__ import annotations

from datetime import date

from hedge_fund.data.service import DataService
from hedge_fund.nlp.news_sentiment import enrich_news_with_sentiment_async


async def assemble_research_snapshot(
    ticker: str,
    ds: DataService,
    *,
    price_days: int = 30,
    end_date: date | None = None,
    as_of_note: str | None = None,
) -> tuple[dict, dict]:
    """Build price summary, fundamentals, technicals, news; return (flat fields, llm snapshot)."""
    fundamentals = ds.get_fundamentals(ticker)
    technicals = ds.get_technical_indicators(ticker)

    df = ds.get_price_history(ticker, days=price_days, end_date=end_date)
    price_summary: dict = {}
    if not df.empty:
        close = df["close"]
        price_summary = {
            "current": float(close.iloc[-1]),
            # Kept for API/frontend compatibility (window length = price_days).
            "change_30d_pct": round(
                (float(close.iloc[-1]) / float(close.iloc[0]) - 1) * 100,
                2,
            ),
            "high_30d": float(close.max()),
            "low_30d": float(close.min()),
            "price_window_days": price_days,
        }

    news = ds.get_news(ticker, limit=5)
    news_list = [{"title": n.get("title", ""), "date": str(n.get("date", ""))} for n in news]
    news_list, news_sentiment = await enrich_news_with_sentiment_async(news_list)

    data_snapshot: dict = {
        "ticker": ticker,
        "price": price_summary,
        "fundamentals": fundamentals,
        "technicals": technicals,
        "news": news_list,
        "news_sentiment": news_sentiment,
    }
    if end_date is not None:
        data_snapshot["as_of_date"] = end_date.isoformat()
    if as_of_note:
        data_snapshot["simulation_note"] = as_of_note

    partial = {
        "ticker": ticker,
        "price": price_summary,
        "fundamentals": fundamentals,
        "technicals": technicals,
        "news": news_list,
        "news_sentiment": news_sentiment,
    }
    return partial, data_snapshot
