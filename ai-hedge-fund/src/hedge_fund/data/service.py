"""Unified data access layer — delegates to ProviderRegistry with fallback chains."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

# Providers read API keys at import time, so the environment has to be loaded
# before they are imported. The order below is deliberate, not accidental.
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from hedge_fund.data.cache import DataCategory  # noqa: E402
from hedge_fund.data.registry import ProviderRegistry  # noqa: E402

logger = logging.getLogger(__name__)


class DataService:
    """Single entry point for all market data.

    All methods delegate to ProviderRegistry which handles:
    - Provider fallback chains (try providers in priority order)
    - TTL caching (per-category expiry)
    - Rate limiting (per-provider token bucket)

    Works with zero API keys (yfinance + pandas-datareader only).
    Gets richer as Finnhub / Twelve Data / Alpha Vantage keys are added.
    """

    def __init__(self) -> None:
        self.registry = ProviderRegistry()

    # ------------------------------------------------------------------
    # Original 5 methods (backward compatible)
    # ------------------------------------------------------------------

    def get_price_history(
        self,
        ticker: str,
        days: int = 365,
        interval: str = "1d",
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV price history.

        If ``end_date`` is set, the window ends on that date (inclusive),
        which supports historical simulation; otherwise the window ends today.
        """
        ed: date | None = end_date
        result = self.registry.get(
            DataCategory.PRICE, ticker, days=days, interval=interval, end_date=ed
        )
        if result is None:
            return pd.DataFrame()
        return result

    def get_fundamentals(self, ticker: str) -> dict:
        """Key fundamental metrics for a ticker."""
        result = self.registry.get(DataCategory.FUNDAMENTALS, ticker)
        if result is None:
            return {"ticker": ticker, "error": "no data"}
        return result

    def get_technical_indicators(self, ticker: str, days: int = 365) -> dict:
        """RSI, MACD, SMA, Bollinger Bands, ATR for a ticker."""
        result = self.registry.get(DataCategory.TECHNICALS, ticker, days=days)
        if result is None:
            return {"ticker": ticker, "error": "no data"}
        return result

    def get_macro_data(self, series_id: str, days: int = 365 * 5) -> pd.DataFrame:
        """Fetch macro time series from FRED."""
        result = self.registry.get(DataCategory.MACRO, series_id, days=days)
        if result is None:
            return pd.DataFrame()
        return result

    def get_news(self, query: str, limit: int = 10) -> list[dict]:
        """Fetch recent news for a query/ticker."""
        result = self.registry.get(DataCategory.NEWS, query, limit=limit)
        if result is None:
            return []
        return result

    def get_bubble_detector(self, days: int = 365 * 10) -> dict:
        """Market-wide bubble detector — composite of macro valuation/complacency gauges.

        Composes existing FRED macro fetches (each individually cached) into
        Buffett Indicator, S&P500/M2, VIX, high-yield spread, and yield-curve gauges.
        """
        from hedge_fund.data.bubble_detector import (
            REQUIRED_SERIES,
            compute_bubble_detector,
        )

        fred = {sid: self.get_macro_data(sid, days=days) for sid in REQUIRED_SERIES}
        return compute_bubble_detector(fred)

    # ------------------------------------------------------------------
    # New methods — 15 additional data categories
    # ------------------------------------------------------------------

    def get_esg(self, ticker: str) -> Any:
        """ESG scores (Finnhub)."""
        return self.registry.get(DataCategory.ESG, ticker)

    def get_insider(self, ticker: str) -> Any:
        """Insider transactions (yfinance → Finnhub)."""
        return self.registry.get(DataCategory.INSIDER, ticker)

    def get_institutional(self, ticker: str) -> Any:
        """Institutional holders (yfinance → Finnhub)."""
        return self.registry.get(DataCategory.INSTITUTIONAL, ticker)

    def get_earnings(self, ticker: str) -> Any:
        """Earnings dates, history, estimates (yfinance → Finnhub)."""
        return self.registry.get(DataCategory.EARNINGS, ticker)

    def get_analyst(self, ticker: str) -> Any:
        """Analyst ratings and price targets (yfinance → Finnhub)."""
        return self.registry.get(DataCategory.ANALYST, ticker)

    def get_sentiment(self, ticker: str) -> Any:
        """News sentiment scores (Finnhub)."""
        return self.registry.get(DataCategory.SENTIMENT, ticker)

    def get_sector_performance(self) -> Any:
        """Real-time sector performance rankings (Alpha Vantage)."""
        return self.registry.get(DataCategory.SECTOR_PERFORMANCE, "__ALL__")

    def get_fama_french(self) -> Any:
        """Fama-French 5-factor data (pandas-datareader)."""
        return self.registry.get(DataCategory.FAMA_FRENCH, "__FF__")

    def get_options(self, ticker: str) -> Any:
        """Options chain data (yfinance)."""
        return self.registry.get(DataCategory.OPTIONS, ticker)

    def get_filings(self, ticker: str) -> Any:
        """SEC filings (Finnhub)."""
        return self.registry.get(DataCategory.SEC_FILINGS, ticker)

    def get_congressional(self, ticker: str) -> Any:
        """Congressional trades (Finnhub)."""
        return self.registry.get(DataCategory.CONGRESSIONAL, ticker)

    def get_peers(self, ticker: str) -> Any:
        """Peer comparison data (yfinance → Finnhub)."""
        return self.registry.get(DataCategory.PEERS, ticker)

    def get_provider_status(self) -> list[dict]:
        """Return status of all registered providers."""
        return self.registry.get_provider_status()

    def get_provider_chain(self, category: str) -> list[str]:
        """Return provider fallback chain for a data category."""
        try:
            cat = DataCategory(category)
            return self.registry.get_chain(cat)
        except ValueError:
            return []


_data_service: DataService | None = None


def get_data_service() -> DataService:
    """Process-wide singleton so HTTP handlers share one cache and rate limiter."""
    global _data_service
    if _data_service is None:
        _data_service = DataService()
    return _data_service
