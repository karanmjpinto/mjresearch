"""Financial Datasets API — optional key; broad US ticker coverage (https://financialdatasets.ai/)."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd

from hedge_fund.data.cache import DataCategory
from hedge_fund.data.providers.base import BaseProvider

logger = logging.getLogger(__name__)

BASE_URL = "https://api.financialdatasets.ai"


class FinancialDatasetsProvider(BaseProvider):
    name = "financial_datasets"
    priority = 2
    categories = {
        DataCategory.PRICE,
        DataCategory.FUNDAMENTALS,
    }

    def available(self) -> bool:
        return bool(os.environ.get("FINANCIAL_DATASETS_API_KEY", "").strip())

    def _headers(self) -> dict[str, str]:
        key = os.environ.get("FINANCIAL_DATASETS_API_KEY", "").strip()
        return {"X-API-KEY": key}

    def fetch(self, category: DataCategory, ticker: str, **kwargs: Any) -> Any:
        dispatch = {
            DataCategory.PRICE: self._price,
            DataCategory.FUNDAMENTALS: self._fundamentals,
        }
        handler = dispatch.get(category)
        if handler is None:
            return None
        try:
            return handler(ticker, **kwargs)
        except Exception as e:
            logger.warning("Financial Datasets %s failed for %s: %s", category.value, ticker, e)
            return None

    def _price(self, ticker: str, **kwargs: Any) -> pd.DataFrame | None:
        days = int(kwargs.get("days", 365))
        end: date = kwargs.get("end_date") or date.today()
        start = end - timedelta(days=days)
        url = f"{BASE_URL}/prices/"
        params = {
            "ticker": ticker.upper().strip(),
            "interval": "day",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        with httpx.Client(timeout=60.0) as client:
            r = client.get(url, headers=self._headers(), params=params)
        if r.status_code >= 400:
            logger.debug("FD prices HTTP %s: %s", r.status_code, r.text[:300])
            return None
        data = r.json()
        rows = data.get("prices") or []
        if not rows:
            return None
        records = []
        for row in rows:
            ts = row.get("time") or row.get("date")
            records.append(
                {
                    "date": ts,
                    "open": float(row.get("open", 0) or 0),
                    "high": float(row.get("high", 0) or 0),
                    "low": float(row.get("low", 0) or 0),
                    "close": float(row.get("close", 0) or 0),
                    "volume": float(row.get("volume", 0) or 0),
                }
            )
        df = pd.DataFrame(records)
        if df.empty:
            return None
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df.columns = [str(c).lower() for c in df.columns]
        return df

    def _fundamentals(self, ticker: str, **kwargs: Any) -> dict | None:
        url = f"{BASE_URL}/company/facts"
        params = {"ticker": ticker.upper().strip()}
        with httpx.Client(timeout=60.0) as client:
            r = client.get(url, headers=self._headers(), params=params)
        if r.status_code >= 400:
            return None
        data = r.json()
        facts = data.get("company_facts")
        if not isinstance(facts, dict) or not facts:
            return None
        return {
            "ticker": ticker.upper().strip(),
            "name": facts.get("name", ticker),
            "sector": facts.get("sector", "N/A"),
            "industry": facts.get("industry", "N/A"),
            "market_cap": facts.get("market_cap"),
            "employees": facts.get("employees"),
            "description": (facts.get("description") or "")[:2000],
            "source": "financial_datasets",
        }
