"""The cache grew without a ceiling, and is now read from several threads.

Both are new requirements rather than refinements. An expired entry used to be
dropped only when something asked for that exact key again, so a process that
served many tickers once each kept every one of them until it restarted. And
the parallel fetches mean two threads can reach the same key at the same
moment.
"""

from __future__ import annotations

import threading
import time

from hedge_fund.data.cache import DEFAULT_TTLS, DataCategory, TTLCache

PRICE = DataCategory.PRICE


def test_a_value_comes_back() -> None:
    c = TTLCache()
    c.set(PRICE, "AAPL", 123)
    assert c.get(PRICE, "AAPL") == 123


def test_an_expired_value_does_not() -> None:
    c = TTLCache(ttls={PRICE: 0})
    c.set(PRICE, "AAPL", 123)
    time.sleep(0.01)
    assert c.get(PRICE, "AAPL") is None


def test_categories_do_not_collide() -> None:
    c = TTLCache()
    c.set(PRICE, "AAPL", "price")
    c.set(DataCategory.NEWS, "AAPL", "news")
    assert c.get(PRICE, "AAPL") == "price"
    assert c.get(DataCategory.NEWS, "AAPL") == "news"


def test_the_store_stops_growing_at_the_bound() -> None:
    c = TTLCache(max_entries=10)
    for i in range(500):
        c.set(PRICE, f"T{i}", i)
    assert c.size <= 10


def test_eviction_drops_the_least_recently_used() -> None:
    c = TTLCache(max_entries=3)
    for k in ("A", "B", "C"):
        c.set(PRICE, k, k)
    c.get(PRICE, "A")  # a read is a use, so A is now the newest
    c.set(PRICE, "D", "D")  # pushes one out, and it must be B
    assert c.get(PRICE, "A") == "A"
    assert c.get(PRICE, "B") is None
    assert c.get(PRICE, "C") == "C"
    assert c.get(PRICE, "D") == "D"


def test_expired_entries_go_before_live_ones() -> None:
    """A live entry costs a fetch to replace; an expired one is free to lose."""
    c = TTLCache(ttls={PRICE: 0, DataCategory.MACRO: 3600}, max_entries=4)
    for i in range(3):
        c.set(PRICE, f"STALE{i}", i)
    time.sleep(0.01)
    c.set(DataCategory.MACRO, "LIVE", "live")
    c.set(DataCategory.MACRO, "LIVE2", "live2")
    assert c.get(DataCategory.MACRO, "LIVE") == "live"
    assert c.get(DataCategory.MACRO, "LIVE2") == "live2"


def test_invalidate_and_clear() -> None:
    c = TTLCache()
    c.set(PRICE, "AAPL", 1)
    c.invalidate(PRICE, "AAPL")
    assert c.get(PRICE, "AAPL") is None
    c.set(PRICE, "MSFT", 1)
    c.clear()
    assert c.size == 0


def test_stats_report_the_ceiling() -> None:
    c = TTLCache(max_entries=64)
    c.set(PRICE, "AAPL", 1)
    s = c.stats()
    assert s["total_entries"] == 1
    assert s["active_entries"] == 1
    assert s["max_entries"] == 64


def test_concurrent_writers_leave_the_store_consistent() -> None:
    """Eight threads hammering one bounded cache must not corrupt it."""
    c = TTLCache(max_entries=50)
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        try:
            for i in range(300):
                c.set(PRICE, f"T{n}-{i}", i)
                c.get(PRICE, f"T{n}-{i}")
                c.stats()
        except BaseException as exc:  # noqa: BLE001 — the test is what it raised
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert c.size <= 50


def test_the_shipped_ttls_are_all_positive() -> None:
    """A zero TTL would make the cache a no-op and every page a cold fetch."""
    assert DEFAULT_TTLS
    assert all(v > 0 for v in DEFAULT_TTLS.values())
