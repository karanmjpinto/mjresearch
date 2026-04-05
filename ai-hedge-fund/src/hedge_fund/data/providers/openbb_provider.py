"""Open Data Platform (OpenBB) provider — unified `obb` API with yfinance backend."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from hedge_fund.data.cache import DataCategory
from hedge_fund.data.providers.base import BaseProvider
from hedge_fund.data.technicals_compute import compute_technicals_from_ohlcv

logger = logging.getLogger(__name__)

_OBB = None
_OBB_ERROR: str | None = None

try:
    from openbb import obb as _obb

    _OBB = _obb
except ImportError as e:
    _OBB_ERROR = str(e)
    logger.info("OpenBB not installed: %s", e)


class OpenBBProvider(BaseProvider):
    name = "openbb"
    priority = 0
    categories = {
        DataCategory.PRICE,
        DataCategory.FUNDAMENTALS,
        DataCategory.TECHNICALS,
        DataCategory.NEWS,
    }

    def available(self) -> bool:
        return _OBB is not None

    def fetch(self, category: DataCategory, ticker: str, **kwargs: Any) -> Any:
        if _OBB is None:
            return None
        dispatch = {
            DataCategory.PRICE: self._price,
            DataCategory.FUNDAMENTALS: self._fundamentals,
            DataCategory.TECHNICALS: self._technicals,
            DataCategory.NEWS: self._news,
        }
        handler = dispatch.get(category)
        if handler is None:
            return None
        try:
            return handler(ticker, **kwargs)
        except Exception as e:
            logger.warning("OpenBB %s failed for %s: %s", category.value, ticker, e)
            return None

    def _price(self, ticker: str, **kwargs: Any) -> pd.DataFrame | None:
        days = int(kwargs.get("days", 365))
        interval = kwargs.get("interval", "1d")
        end: date = kwargs.get("end_date") or date.today()
        start = end - timedelta(days=days)
        r = _OBB.equity.price.historical(
            symbol=ticker,
            provider="yfinance",
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            interval=interval,
        )
        df = r.to_dataframe()
        if df.empty:
            return None
        df.columns = [str(c).lower() for c in df.columns]
        return df

    def _fundamentals(self, ticker: str, **kwargs: Any) -> dict | None:
        m = _OBB.equity.fundamental.metrics(ticker, provider="yfinance").to_dataframe()
        if m.empty:
            return None
        row = m.iloc[0]

        p = _OBB.equity.profile(ticker, provider="yfinance").to_dataframe()
        prow = p.iloc[0] if not p.empty else None

        name = str(prow["name"]) if prow is not None and "name" in prow.index else ticker
        sector = (
            str(prow["sector"])
            if prow is not None and "sector" in prow.index
            else "N/A"
        )
        industry = (
            str(prow["industry_category"])
            if prow is not None and "industry_category" in prow.index
            else "N/A"
        )
        exch = (
            str(prow["stock_exchange"])
            if prow is not None and "stock_exchange" in prow.index
            else None
        )

        def _cell(col: str) -> Any:
            if col not in row.index:
                return None
            v = row[col]
            if pd.isna(v):
                return None
            return v.item() if hasattr(v, "item") else v

        return {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "industry": industry,
            "market_cap": _cell("market_cap"),
            "pe_ratio": _cell("pe_ratio"),
            "forward_pe": _cell("forward_pe"),
            "peg_ratio": _cell("peg_ratio_ttm"),
            "price_to_book": _cell("price_to_book"),
            "dividend_yield": _cell("dividend_yield"),
            "beta": _cell("beta"),
            "52w_high": None,
            "52w_low": None,
            "avg_volume": None,
            "currency": str(_cell("currency") or "USD"),
            "exchange": exch,
            "revenue": None,
            "net_income": None,
            "ebitda": None,
            "free_cash_flow": None,
            "operating_cash_flow": None,
            "total_assets": None,
            "total_debt": None,
            "total_equity": None,
            "source": "openbb",
        }

    def _technicals(self, ticker: str, **kwargs: Any) -> dict | None:
        df = self._price(ticker, days=365, interval="1d")
        out = compute_technicals_from_ohlcv(df, ticker, source="openbb")
        return out

    def _news(self, ticker: str, **kwargs: Any) -> list[dict] | None:
        limit = int(kwargs.get("limit", 10))
        r = _OBB.news.company(ticker, provider="yfinance", limit=limit)
        df = r.to_dataframe()
        if df.empty:
            return []
        df = df.head(limit)
        out: list[dict] = []
        for _, row in df.iterrows():
            pub = row.name if hasattr(row, "name") else None
            out.append(
                {
                    "title": str(row.get("title", "") or ""),
                    "publisher": str(row.get("source", "") or ""),
                    "link": str(row.get("url", "") or ""),
                    "published": str(pub) if pub is not None else "",
                    "date": str(pub) if pub is not None else "",
                    "type": "",
                    "source": "openbb",
                }
            )
        return out

    def status(self) -> dict:
        """Include import error when OpenBB is unavailable."""
        s = super().status()
        if _OBB_ERROR:
            s["import_error"] = _OBB_ERROR
        return s
