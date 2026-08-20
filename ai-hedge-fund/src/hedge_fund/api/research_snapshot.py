"""Shared research snapshot builder for /research/check and /simulation/backtest.

The snapshot is the unit of analysis. Everything downstream — personas, the
committee, the plan executor, the claim verifier — reads this object and nothing
else, so two runs over the same snapshot see byte-identical inputs. It carries
its own provenance (which provider answered each slot, and what shape the answer
had) because a fallback chain can change sources between two otherwise identical
runs and nothing else would notice.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from hedge_fund.data.provenance import capture
from hedge_fund.data.service import DataService
from hedge_fund.nlp.news_sentiment import enrich_news_with_sentiment_async


def summarize_data_quality(provenance: dict[str, Any]) -> dict[str, Any]:
    """Condense provenance into a few fields the UI can show without unpacking it."""
    warnings = provenance.get("warnings", []) or []
    slots = provenance.get("slots", {}) or {}
    unresolved = sorted(k for k, v in slots.items() if not v.get("provider"))
    return {
        "providers_used": provenance.get("providers_used", []),
        "warning_count": len(warnings),
        "warnings": warnings,
        "unresolved_slots": unresolved,
        "cache_hits": provenance.get("cache_hits", 0),
        "fetch_count": provenance.get("fetch_count", 0),
    }


async def assemble_research_snapshot(
    ticker: str,
    ds: DataService,
    *,
    price_days: int = 30,
    end_date: date | None = None,
    as_of_note: str | None = None,
) -> tuple[dict, dict]:
    """Build price summary, fundamentals, technicals, news; return (flat fields, llm snapshot)."""
    with capture() as prov:
        fundamentals = ds.get_fundamentals(ticker)
        technicals = ds.get_technical_indicators(ticker)

        df = ds.get_price_history(ticker, days=price_days, end_date=end_date)
        price_summary: dict = {}
        if not df.empty:
            close = df["close"]
            price_summary = {
                "current": float(close.iloc[-1]),
                # Window length is price_days; the *_30d names are kept for
                # API/frontend compatibility.
                "change_30d_pct": round(
                    (float(close.iloc[-1]) / float(close.iloc[0]) - 1) * 100,
                    2,
                ),
                "high_30d": float(close.max()),
                "low_30d": float(close.min()),
                "price_window_days": price_days,
                "observations": int(len(close)),
                "window_start": str(df.index.min())[:10],
                "window_end": str(df.index.max())[:10],
            }

        news = ds.get_news(ticker, limit=5)
        news_list = [{"title": n.get("title", ""), "date": str(n.get("date", ""))} for n in news]
        news_list, news_sentiment = await enrich_news_with_sentiment_async(news_list)

    provenance = prov.as_dict()
    data_quality = summarize_data_quality(provenance)

    data_snapshot: dict = {
        "ticker": ticker,
        "price": price_summary,
        "fundamentals": fundamentals,
        "technicals": technicals,
        "news": news_list,
        "news_sentiment": news_sentiment,
        "provenance": provenance,
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
        "data_quality": data_quality,
    }
    return partial, data_snapshot
