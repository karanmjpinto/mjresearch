"""Twelve Data provider — 100+ technical indicators, batch mode."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

import pandas as pd

from hedge_fund.data.cache import DataCategory
from hedge_fund.data.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class TwelveDataProvider(BaseProvider):
    name = "twelvedata"
    priority = 3
    categories = {
        DataCategory.TECHNICALS,
        DataCategory.PRICE,
    }

    def __init__(self) -> None:
        self._td = None
        api_key = os.getenv("TWELVEDATA_API_KEY", "")
        if api_key:
            try:
                from twelvedata import TDClient

                self._td = TDClient(apikey=api_key)
            except ImportError:
                logger.info("twelvedata not installed")
        else:
            logger.info("TWELVEDATA_API_KEY not set — Twelve Data provider disabled")

    def available(self) -> bool:
        return self._td is not None

    def fetch(self, category: DataCategory, ticker: str, **kwargs: Any) -> Any:
        if category == DataCategory.TECHNICALS:
            return self._technicals(ticker, **kwargs)
        elif category == DataCategory.PRICE:
            return self._price(ticker, **kwargs)
        return None

    def _price(self, ticker: str, **kwargs: Any) -> pd.DataFrame | None:
        """Fetch price data via Twelve Data."""
        days = kwargs.get("days", 365)
        interval = kwargs.get("interval", "1day")

        # Map common intervals
        interval_map = {"1d": "1day", "1h": "1h", "5m": "5min", "1m": "1min"}
        interval = interval_map.get(interval, interval)

        try:
            ts = self._td.time_series(
                symbol=ticker,
                interval=interval,
                outputsize=min(days, 5000),
            )
            df = ts.as_pandas()
            if df is None or df.empty:
                return None

            df.columns = [c.lower() for c in df.columns]
            return df
        except Exception as e:
            logger.warning("Twelve Data price error for %s: %s", ticker, e)
            return None

    def _technicals(self, ticker: str, **kwargs: Any) -> dict | None:
        """Fetch rich technical indicators via Twelve Data."""
        try:
            # Build a time series with multiple indicators
            ts = self._td.time_series(
                symbol=ticker,
                interval="1day",
                outputsize=200,
            )

            # Fetch individual indicators
            rsi = self._td.rsi(symbol=ticker, interval="1day", time_period=14).as_json()
            macd = self._td.macd(symbol=ticker, interval="1day").as_json()
            bbands = self._td.bbands(symbol=ticker, interval="1day", time_period=20).as_json()
            sma50 = self._td.sma(symbol=ticker, interval="1day", time_period=50).as_json()
            sma200 = self._td.sma(symbol=ticker, interval="1day", time_period=200).as_json()
            atr = self._td.atr(symbol=ticker, interval="1day", time_period=14).as_json()
            adx = self._td.adx(symbol=ticker, interval="1day", time_period=14).as_json()
            stoch = self._td.stoch(symbol=ticker, interval="1day").as_json()
            cci = self._td.cci(symbol=ticker, interval="1day", time_period=20).as_json()

            def _latest(data, key=None):
                if not data or not isinstance(data, list):
                    return None
                latest = data[0] if data else None
                if latest is None:
                    return None
                if key:
                    return _safe_float(latest.get(key))
                return latest

            result = {
                "ticker": ticker,
                "rsi_14": _latest(rsi, "rsi"),
                "macd": {
                    "line": _latest(macd, "macd"),
                    "signal": _latest(macd, "macd_signal"),
                    "histogram": _latest(macd, "macd_hist"),
                },
                "bollinger": {
                    "upper": _latest(bbands, "upper_band"),
                    "middle": _latest(bbands, "middle_band"),
                    "lower": _latest(bbands, "lower_band"),
                },
                "sma_50": _latest(sma50, "sma"),
                "sma_200": _latest(sma200, "sma"),
                "atr_14": _latest(atr, "atr"),
                "adx_14": _latest(adx, "adx"),
                "stochastic": {
                    "k": _latest(stoch, "slow_k"),
                    "d": _latest(stoch, "slow_d"),
                },
                "cci_20": _latest(cci, "cci"),
                "source": "twelvedata",
            }
            return result
        except Exception as e:
            logger.warning("Twelve Data technicals error for %s: %s", ticker, e)
            return None


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return round(f, 4) if f == f else None
    except (ValueError, TypeError):
        return None
