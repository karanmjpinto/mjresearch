"""Finnhub provider — ESG, sentiment, SEC filings, congressional trades."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

from hedge_fund.data.cache import DataCategory
from hedge_fund.data.models import (
    CongressionalTrade,
    ESGScores,
    InsiderTransaction,
    NewsSentiment,
    SECFiling,
)
from hedge_fund.data.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class FinnhubProvider(BaseProvider):
    name = "finnhub"
    priority = 2
    categories = {
        DataCategory.ESG,
        DataCategory.NEWS,
        DataCategory.SENTIMENT,
        DataCategory.SEC_FILINGS,
        DataCategory.CONGRESSIONAL,
        DataCategory.INSIDER,
        DataCategory.ANALYST,
    }

    def __init__(self) -> None:
        self._client = None
        api_key = os.getenv("FINNHUB_API_KEY", "")
        if api_key:
            try:
                import finnhub

                self._client = finnhub.Client(api_key=api_key)
            except ImportError:
                logger.info("finnhub-python not installed")
        else:
            logger.info("FINNHUB_API_KEY not set — Finnhub provider disabled")

    def available(self) -> bool:
        return self._client is not None

    def fetch(self, category: DataCategory, ticker: str, **kwargs: Any) -> Any:
        dispatch = {
            DataCategory.ESG: self._esg,
            DataCategory.NEWS: self._news,
            DataCategory.SENTIMENT: self._sentiment,
            DataCategory.SEC_FILINGS: self._filings,
            DataCategory.CONGRESSIONAL: self._congressional,
            DataCategory.INSIDER: self._insider,
            DataCategory.ANALYST: self._analyst,
        }
        handler = dispatch.get(category)
        if handler is None:
            return None
        return handler(ticker, **kwargs)

    # ------------------------------------------------------------------
    # ESG
    # ------------------------------------------------------------------

    def _esg(self, ticker: str, **kwargs: Any) -> ESGScores | None:
        try:
            data = self._client.company_esg_score(symbol=ticker)
            if not data or not data.get("data"):
                return None

            scores = data["data"][-1] if isinstance(data["data"], list) else data["data"]
            return ESGScores(
                ticker=ticker,
                total_score=_safe_float(scores.get("totalScore")),
                environment_score=_safe_float(scores.get("environmentScore")),
                social_score=_safe_float(scores.get("socialScore")),
                governance_score=_safe_float(scores.get("governanceScore")),
                source="finnhub",
            )
        except Exception as e:
            logger.warning("Finnhub ESG error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------

    def _news(self, ticker: str, **kwargs: Any) -> list[dict] | None:
        limit = kwargs.get("limit", 10)
        try:
            end = date.today()
            start = end - timedelta(days=7)
            news = self._client.company_news(
                ticker,
                _from=start.isoformat(),
                to=end.isoformat(),
            )
            if not news:
                return None

            results = []
            for item in news[:limit]:
                results.append({
                    "title": item.get("headline", ""),
                    "publisher": item.get("source", ""),
                    "link": item.get("url", ""),
                    "published": item.get("datetime", ""),
                    "summary": item.get("summary", ""),
                    "category": item.get("category", ""),
                    "source": "finnhub",
                })
            return results if results else None
        except Exception as e:
            logger.warning("Finnhub news error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Sentiment
    # ------------------------------------------------------------------

    def _sentiment(self, ticker: str, **kwargs: Any) -> NewsSentiment | None:
        try:
            data = self._client.news_sentiment(ticker)
            if not data or not data.get("sentiment"):
                return None

            sentiment = data["sentiment"]
            buzz = data.get("buzz", {})

            return NewsSentiment(
                ticker=ticker,
                buzz_score=_safe_float(buzz.get("buzz")),
                articles_in_last_week=buzz.get("articlesInLastWeek"),
                weekly_average=_safe_float(buzz.get("weeklyAverage")),
                company_news_score=_safe_float(data.get("companyNewsScore")),
                sector_avg_bullish=_safe_float(sentiment.get("sectorAverageBullishPercent")),
                sector_avg_news_score=_safe_float(sentiment.get("sectorAverageNewsScore")),
                bearish_pct=_safe_float(sentiment.get("bearishPercent")),
                bullish_pct=_safe_float(sentiment.get("bullishPercent")),
                source="finnhub",
            )
        except Exception as e:
            logger.warning("Finnhub sentiment error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # SEC Filings
    # ------------------------------------------------------------------

    def _filings(self, ticker: str, **kwargs: Any) -> list[SECFiling] | None:
        try:
            filings = self._client.filings(symbol=ticker)
            if not filings:
                return None

            results = []
            for f in filings[:20]:
                results.append(SECFiling(
                    ticker=ticker,
                    form_type=f.get("form", ""),
                    filed_date=f.get("filedDate"),
                    accepted_date=f.get("acceptedDate"),
                    report_url=f.get("reportUrl", ""),
                    filing_url=f.get("filingUrl", ""),
                    source="finnhub",
                ))
            return results if results else None
        except Exception as e:
            logger.warning("Finnhub filings error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Congressional Trades
    # ------------------------------------------------------------------

    def _congressional(self, ticker: str, **kwargs: Any) -> list[CongressionalTrade] | None:
        try:
            data = self._client.stock_lobbying(symbol=ticker)
            if not data or not data.get("data"):
                return None

            results = []
            for item in data["data"][:20]:
                results.append(CongressionalTrade(
                    ticker=ticker,
                    representative=item.get("name", "Unknown"),
                    transaction_type=item.get("transactionType", ""),
                    amount_range=item.get("transactionAmount", ""),
                    transaction_date=item.get("transactionDate"),
                    source="finnhub",
                ))
            return results if results else None
        except Exception as e:
            logger.warning("Finnhub congressional error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Insider Transactions
    # ------------------------------------------------------------------

    def _insider(self, ticker: str, **kwargs: Any) -> list[InsiderTransaction] | None:
        try:
            data = self._client.stock_insider_transactions(symbol=ticker)
            if not data or not data.get("data"):
                return None

            results = []
            for item in data["data"][:20]:
                results.append(InsiderTransaction(
                    ticker=ticker,
                    name=item.get("name", "Unknown"),
                    transaction_type=item.get("transactionType", ""),
                    shares=item.get("share", 0),
                    value=_safe_float(item.get("transactionPrice")),
                    date=item.get("transactionDate"),
                    source="finnhub",
                ))
            return results if results else None
        except Exception as e:
            logger.warning("Finnhub insider error for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Analyst
    # ------------------------------------------------------------------

    def _analyst(self, ticker: str, **kwargs: Any) -> list[dict] | None:
        try:
            recs = self._client.recommendation_trends(symbol=ticker)
            if not recs:
                return None

            results = []
            for r in recs[:6]:
                results.append({
                    "period": r.get("period", ""),
                    "strong_buy": r.get("strongBuy", 0),
                    "buy": r.get("buy", 0),
                    "hold": r.get("hold", 0),
                    "sell": r.get("sell", 0),
                    "strong_sell": r.get("strongSell", 0),
                    "source": "finnhub",
                })
            return results if results else None
        except Exception as e:
            logger.warning("Finnhub analyst error for %s: %s", ticker, e)
            return None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return f if f == f else None  # NaN check
    except (ValueError, TypeError):
        return None
