"""Bullpen.News provider — buy-side commentary per ticker, and the daily feed.

No key. One request per ticker, rate-limited in ``config/providers.json`` and
cached for six hours: Bullpen's terms ask that nobody scrape at a rate that
costs them money, and a screen over 500 names must not become that.
"""

from __future__ import annotations

from typing import Any

import httpx

from hedge_fund.data import bullpen
from hedge_fund.data.cache import DataCategory
from hedge_fund.data.providers.base import BaseProvider


class BullpenProvider(BaseProvider):
    name = "bullpen"
    priority = 1
    categories = {DataCategory.COMMENTARY}

    def available(self) -> bool:
        return True

    def fetch(self, category: DataCategory, ticker: str, **kwargs: Any) -> Any:
        if category != DataCategory.COMMENTARY:
            return None
        if ticker == bullpen.FEED_KEY:
            return bullpen.fetch_feed() or None
        try:
            return bullpen.fetch_ticker(ticker)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
