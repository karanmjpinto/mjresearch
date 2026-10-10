"""TTL cache with per-category expiry for data provider results."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
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


#: Most entries this cache will hold. Beyond it, the least recently used entry
#: goes. A bound is necessary rather than tidy: an expired entry was only
#: dropped when something asked for that exact key again, so a process that
#: serves many tickers once each kept every one of them for the life of the
#: process. 4096 frames of daily prices is tens of megabytes, which is a
#: ceiling the container can afford, and the working set of a session is far
#: smaller than that.
MAX_ENTRIES = 4096


class TTLCache:
    """In-memory cache with per-category TTL expiration and an LRU bound.

    Safe to share across threads. That matters because the price fetches now
    run side by side in a worker pool: two threads reaching a plain dict at the
    same moment can both miss, both fetch, and then race on the write.
    """

    def __init__(
        self,
        ttls: dict[DataCategory, int] | None = None,
        max_entries: int = MAX_ENTRIES,
    ) -> None:
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._ttls = {**DEFAULT_TTLS, **(ttls or {})}
        self._max_entries = max(1, max_entries)
        self._lock = threading.Lock()

    def _make_key(self, category: DataCategory, key: str) -> str:
        return f"{category.value}:{key}"

    def get(self, category: DataCategory, key: str) -> Any | None:
        """Return cached value if not expired, else None."""
        cache_key = self._make_key(category, key)
        with self._lock:
            entry = self._store.get(cache_key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[cache_key]
                return None
            # A read is a use, so it moves to the newest end and survives the
            # next eviction.
            self._store.move_to_end(cache_key)
            return value

    def set(self, category: DataCategory, key: str, value: Any) -> None:
        """Store value with category-specific TTL, and evict if over the bound."""
        cache_key = self._make_key(category, key)
        ttl = self._ttls.get(category, 3600)
        with self._lock:
            self._store[cache_key] = (time.monotonic() + ttl, value)
            self._store.move_to_end(cache_key)
            if len(self._store) > self._max_entries:
                self._evict_locked()

    def _evict_locked(self) -> None:
        """Drop expired entries first, then the oldest. Caller holds the lock.

        Expired first because they are free to lose, and a sweep is cheap next
        to the fetch that refills a live entry.
        """
        now = time.monotonic()
        for k in [k for k, (exp, _) in self._store.items() if now > exp]:
            del self._store[k]
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def invalidate(self, category: DataCategory, key: str) -> None:
        """Remove a specific entry."""
        cache_key = self._make_key(category, key)
        with self._lock:
            self._store.pop(cache_key, None)

    def clear(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def stats(self) -> dict:
        """Return cache statistics."""
        now = time.monotonic()
        with self._lock:
            total = len(self._store)
            expired = sum(1 for exp, _ in self._store.values() if now > exp)
        return {
            "total_entries": total,
            "expired_entries": expired,
            "active_entries": total - expired,
            "max_entries": self._max_entries,
        }
