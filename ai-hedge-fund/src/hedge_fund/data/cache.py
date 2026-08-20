"""TTL cache with per-category expiry for data provider results."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DataCategory(str, Enum):
    """All data categories the system supports."""

    PRICE = "price"
    FUNDAMENTALS = "fundamentals"
    TECHNICALS = "technicals"
    MACRO = "macro"
    NEWS = "news"
    ESG = "esg"
    INSIDER = "insider"
    INSTITUTIONAL = "institutional"
    EARNINGS = "earnings"
    ANALYST = "analyst"
    SENTIMENT = "sentiment"
    SECTOR_PERFORMANCE = "sector_performance"
    FAMA_FRENCH = "fama_french"
    OPTIONS = "options"
    SEC_FILINGS = "sec_filings"
    CONGRESSIONAL = "congressional"
    PEERS = "peers"


# Default TTLs in seconds per category
DEFAULT_TTLS: dict[DataCategory, int] = {
    DataCategory.PRICE: 300,  # 5 min
    DataCategory.FUNDAMENTALS: 3600,  # 1 hr
    DataCategory.TECHNICALS: 900,  # 15 min
    DataCategory.MACRO: 86400,  # 24 hr
    DataCategory.NEWS: 1800,  # 30 min
    DataCategory.ESG: 86400,  # 24 hr
    DataCategory.INSIDER: 3600,  # 1 hr
    DataCategory.INSTITUTIONAL: 21600,  # 6 hr
    DataCategory.EARNINGS: 3600,  # 1 hr
    DataCategory.ANALYST: 21600,  # 6 hr
    DataCategory.SENTIMENT: 1800,  # 30 min
    DataCategory.SECTOR_PERFORMANCE: 3600,  # 1 hr
    DataCategory.FAMA_FRENCH: 86400,  # 24 hr
    DataCategory.OPTIONS: 900,  # 15 min
    DataCategory.SEC_FILINGS: 86400,  # 24 hr
    DataCategory.CONGRESSIONAL: 86400,  # 24 hr
    DataCategory.PEERS: 86400,  # 24 hr
}


@dataclass(frozen=True)
class CachedValue:
    """A cached payload plus the identity of the source that produced it.

    Provider attribution has to survive caching: a cache hit that reports no
    provider is indistinguishable from a fallback silently changing sources.
    """

    value: Any
    provider: str | None = None
    fetched_at: str | None = None
    checks: dict[str, Any] = field(default_factory=dict)


class TTLCache:
    """Simple in-memory cache with per-category TTL expiration."""

    def __init__(self, ttls: dict[DataCategory, int] | None = None) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._ttls = {**DEFAULT_TTLS, **(ttls or {})}

    def _make_key(self, category: DataCategory, key: str) -> str:
        return f"{category.value}:{key}"

    def get(self, category: DataCategory, key: str) -> Any | None:
        """Return cached value if not expired, else None."""
        cache_key = self._make_key(category, key)
        entry = self._store.get(cache_key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[cache_key]
            return None
        return value

    def set(self, category: DataCategory, key: str, value: Any) -> None:
        """Store value with category-specific TTL."""
        cache_key = self._make_key(category, key)
        ttl = self._ttls.get(category, 3600)
        self._store[cache_key] = (time.monotonic() + ttl, value)

    def invalidate(self, category: DataCategory, key: str) -> None:
        """Remove a specific entry."""
        cache_key = self._make_key(category, key)
        self._store.pop(cache_key, None)

    def clear(self) -> None:
        """Clear all cached data."""
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    def stats(self) -> dict:
        """Return cache statistics."""
        now = time.monotonic()
        expired = sum(1 for exp, _ in self._store.values() if now > exp)
        return {
            "total_entries": len(self._store),
            "expired_entries": expired,
            "active_entries": len(self._store) - expired,
        }
