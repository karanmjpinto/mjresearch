"""pandas-datareader provider — FRED macro data + Fama-French factors."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from hedge_fund.data.cache import DataCategory
from hedge_fund.data.models import FamaFrenchFactors
from hedge_fund.data.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class PandasDataReaderProvider(BaseProvider):
    name = "pandas_datareader"
    priority = 1
    categories = {
        DataCategory.MACRO,
        DataCategory.FAMA_FRENCH,
    }

    def __init__(self) -> None:
        self._pdr = None
        try:
            import pandas_datareader as pdr

            self._pdr = pdr
        except ImportError:
            logger.info("pandas-datareader not installed — FRED/Fama-French unavailable")

    def available(self) -> bool:
        return self._pdr is not None

    def fetch(self, category: DataCategory, key: str, **kwargs: Any) -> Any:
        if category == DataCategory.MACRO:
            return self._macro(key, **kwargs)
        elif category == DataCategory.FAMA_FRENCH:
            return self._fama_french(**kwargs)
        return None

    def _macro(self, series_id: str, **kwargs: Any) -> pd.DataFrame | None:
        """Fetch FRED time series."""
        days = kwargs.get("days", 365 * 5)
        end = date.today()
        start = end - timedelta(days=days)
        try:
            df = self._pdr.DataReader(series_id, "fred", start=start, end=end)
            if df.empty:
                return None
            return df
        except Exception as e:
            logger.warning("FRED error for %s: %s", series_id, e)
            return None

    def _fama_french(self, **kwargs: Any) -> FamaFrenchFactors | None:
        """Fetch Fama-French 5-factor data."""
        try:
            data = self._pdr.DataReader("F-F_Research_Data_5_Factors_2x3", "famafrench")
            # data is a dict with integer keys; 0 = monthly, 1 = annual
            monthly = data[0]
            if monthly.empty:
                return None

            # Get last 60 months
            recent = monthly.tail(60)
            factors = []
            for idx, row in recent.iterrows():
                factors.append(
                    {
                        "date": str(idx),
                        "Mkt-RF": round(float(row.get("Mkt-RF", 0)), 4),
                        "SMB": round(float(row.get("SMB", 0)), 4),
                        "HML": round(float(row.get("HML", 0)), 4),
                        "RMW": round(float(row.get("RMW", 0)), 4),
                        "CMA": round(float(row.get("CMA", 0)), 4),
                        "RF": round(float(row.get("RF", 0)), 4),
                    }
                )

            return FamaFrenchFactors(
                period="monthly",
                factors=factors,
                source="pandas-datareader",
            )
        except Exception as e:
            logger.warning("Fama-French error: %s", e)
            return None
