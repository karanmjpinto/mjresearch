"""Alpha Vantage provider — sector performance, intraday data."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
import pandas as pd

from hedge_fund.data.cache import DataCategory
from hedge_fund.data.models import SectorPerformance
from hedge_fund.data.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class AlphaVantageProvider(BaseProvider):
    name = "alpha_vantage"
    priority = 4
    categories = {
        DataCategory.SECTOR_PERFORMANCE,
        DataCategory.PRICE,
    }

    def __init__(self) -> None:
        self._key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
        self._ts = None
        if self._key:
            try:
                from alpha_vantage.timeseries import TimeSeries

                self._ts = TimeSeries(key=self._key, output_format="pandas")
            except ImportError:
                logger.info("alpha_vantage package not installed")
        else:
            logger.info("ALPHA_VANTAGE_API_KEY not set — Alpha Vantage provider disabled")

    def available(self) -> bool:
        # Sector uses HTTP `SECTOR` endpoint; price needs TimeSeries.
        return bool(self._key)

    def fetch(self, category: DataCategory, ticker: str, **kwargs: Any) -> Any:
        if category == DataCategory.SECTOR_PERFORMANCE:
            return self._sector_performance(**kwargs)
        elif category == DataCategory.PRICE:
            return self._price(ticker, **kwargs)
        return None

    def _sector_performance(self, **kwargs: Any) -> SectorPerformance | None:
        """Fetch real-time sector performance rankings (REST `SECTOR` — no legacy module)."""
        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.get(
                    "https://www.alphavantage.co/query",
                    params={"function": "SECTOR", "apikey": self._key},
                )
                r.raise_for_status()
                data = r.json()
            if "Note" in data or "Information" in data:
                logger.warning("Alpha Vantage rate limit or info: %s", data)
                return None

            # As of this writing Alpha Vantage answers `function=SECTOR` with a
            # bare `{}` on a valid, non-rate-limited key: the endpoint has been
            # retired. Say so, rather than returning an object whose every
            # period is empty — the panel would read that as "no sector moved",
            # which is a claim about the market instead of a gap in the feed.
            if not any(k.startswith("Rank ") for k in data):
                logger.warning(
                    "Alpha Vantage returned no sector ranks (keys: %s). The SECTOR "
                    "endpoint appears to be retired; sector drift is unavailable.",
                    sorted(data) or "none",
                )
                return None

            def _parse_sector_data(period_data: dict) -> list[dict]:
                if not period_data:
                    return []
                return [
                    {
                        "sector": k,
                        "change_pct": float(v.strip("%")) if isinstance(v, str) else float(v),
                    }
                    for k, v in period_data.items()
                ]

            return SectorPerformance(
                realtime=_parse_sector_data(data.get("Rank A: Real-Time Performance", {})),
                one_day=_parse_sector_data(data.get("Rank B: 1 Day Performance", {})),
                five_day=_parse_sector_data(data.get("Rank C: 5 Day Performance", {})),
                one_month=_parse_sector_data(data.get("Rank D: 1 Month Performance", {})),
                three_month=_parse_sector_data(data.get("Rank E: 3 Month Performance", {})),
                ytd=_parse_sector_data(data.get("Rank F: Year-to-Date (YTD) Performance", {})),
                one_year=_parse_sector_data(data.get("Rank G: 1 Year Performance", {})),
                source="alpha_vantage",
            )
        except Exception as e:
            logger.warning("Alpha Vantage sector performance error: %s", e)
            return None

    def _price(self, ticker: str, **kwargs: Any) -> pd.DataFrame | None:
        """Fetch intraday price data."""
        if self._ts is None:
            return None
        interval = kwargs.get("interval", "1d")

        try:
            if interval in ("1m", "5m", "15m", "30m", "60m"):
                # Map to Alpha Vantage intervals
                av_interval = interval.replace("m", "min")
                df, _ = self._ts.get_intraday(
                    symbol=ticker,
                    interval=av_interval,
                    outputsize="compact",
                )
            else:
                df, _ = self._ts.get_daily(symbol=ticker, outputsize="compact")

            if df is None or df.empty:
                return None

            # Standardize column names
            df.columns = [c.split(". ")[-1].lower() for c in df.columns]
            return df
        except Exception as e:
            logger.warning("Alpha Vantage price error for %s: %s", ticker, e)
            return None
