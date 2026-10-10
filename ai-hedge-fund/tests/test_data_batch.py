"""Parallel fetching has to be faster, and has to change nothing else.

The speed is the easy half. The hard half is that the four callers it replaced
each had a failure policy, and none of them may change: one unavailable ticker
is that ticker's problem, the basket still answers, and the caller still gets
to call the absence an exclusion or a 422.
"""

from __future__ import annotations

import threading
import time

import pandas as pd
import pytest

from hedge_fund.data.batch import fetch_prices, map_concurrent

IDX = pd.date_range("2024-01-01", periods=5, freq="D")


def _frame(value: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame({"close": [value] * 5}, index=IDX)


class SleepyService:
    """A provider chain whose only cost is waiting, which is the real case."""

    def __init__(self, delay: float = 0.20, fails: set[str] | None = None) -> None:
        self.delay = delay
        self.fails = fails or set()
        self.calls: list[str] = []
        self.peak = 0
        self._live = 0
        self._lock = threading.Lock()

    def get_price_history(self, ticker, days=365, interval="1d", end_date=None):
        with self._lock:
            self.calls.append(ticker)
            self._live += 1
            self.peak = max(self.peak, self._live)
        try:
            time.sleep(self.delay)
            if ticker in self.fails:
                raise RuntimeError(f"{ticker} is unavailable")
            return _frame(float(len(ticker)))
        finally:
            with self._lock:
                self._live -= 1


def test_the_calls_actually_overlap() -> None:
    """Eight waits of 0.2s take about 0.2s, not 1.6s."""
    ds = SleepyService(delay=0.20)
    tickers = ["A", "B", "C", "D", "E", "F", "G", "H"]

    start = time.perf_counter()
    out = fetch_prices(tickers, days=30, data_service=ds)
    elapsed = time.perf_counter() - start

    assert set(out) == set(tickers)
    assert ds.peak == 8, f"only {ds.peak} calls were ever in flight at once"
    assert elapsed < 0.20 * 3, f"{elapsed:.2f}s — the calls did not overlap"


def test_one_bad_ticker_does_not_take_down_the_basket() -> None:
    ds = SleepyService(delay=0.01, fails={"BAD"})
    out = fetch_prices(["GOOD", "BAD", "ALSOGOOD"], days=30, data_service=ds)
    assert set(out) == {"GOOD", "ALSOGOOD"}


def test_an_empty_frame_is_an_absence_not_an_entry() -> None:
    """A caller checks `in`, so a provider's empty answer must not look present."""

    class EmptyService:
        def get_price_history(self, ticker, days=365, **k):
            return pd.DataFrame() if ticker == "NONE" else _frame()

    out = fetch_prices(["HAS", "NONE"], days=30, data_service=EmptyService())
    assert set(out) == {"HAS"}


def test_none_is_also_an_absence() -> None:
    class NoneService:
        def get_price_history(self, ticker, days=365, **k):
            return None if ticker == "NONE" else _frame()

    out = fetch_prices(["HAS", "NONE"], days=30, data_service=NoneService())
    assert set(out) == {"HAS"}


def test_duplicates_are_fetched_once() -> None:
    ds = SleepyService(delay=0.01)
    out = fetch_prices(["AAA", "BBB", "AAA", "AAA"], days=30, data_service=ds)
    assert sorted(ds.calls) == ["AAA", "BBB"]
    assert set(out) == {"AAA", "BBB"}


def test_result_keeps_the_order_asked_for() -> None:
    """A basket's report reads in the caller's order, not completion order."""
    ds = SleepyService(delay=0.01)
    tickers = ["ZZZ", "AAA", "MMM"]
    assert list(fetch_prices(tickers, days=30, data_service=ds)) == tickers


def test_no_tickers_makes_no_calls() -> None:
    ds = SleepyService(delay=5.0)
    assert fetch_prices([], days=30, data_service=ds) == {}
    assert ds.calls == []


def test_a_single_ticker_skips_the_pool() -> None:
    """One name is the common case on the single-ticker routes; it must not
    pay for a thread pool it cannot use."""
    ds = SleepyService(delay=0.01)
    out = fetch_prices(["ONLY"], days=30, data_service=ds)
    assert set(out) == {"ONLY"}
    assert ds.peak == 1


def test_default_interval_and_end_date_are_not_forwarded() -> None:
    """So a service object with a narrower signature still works."""

    class NarrowService:
        def get_price_history(self, ticker, days=365):
            return _frame()

    assert set(fetch_prices(["X", "Y"], days=30, data_service=NarrowService())) == {"X", "Y"}


def test_a_non_default_interval_is_forwarded() -> None:
    seen: dict[str, object] = {}

    class RecordingService:
        def get_price_history(self, ticker, days=365, interval="1d", end_date=None):
            seen[ticker] = (days, interval, end_date)
            return _frame()

    fetch_prices(["X"], days=900, interval="1mo", data_service=RecordingService())
    assert seen["X"] == (900, "1mo", None)


def test_map_concurrent_reports_failures_as_absences() -> None:
    def half(n: int) -> int:
        if n == 0:
            raise ZeroDivisionError("nope")
        return 100 // n

    assert map_concurrent([1, 2, 0, 4], half) == {1: 100, 2: 50, 4: 25}


@pytest.mark.parametrize("workers", [1, 2, 16])
def test_worker_count_changes_speed_not_answers(workers: int) -> None:
    ds = SleepyService(delay=0.01)
    tickers = ["A", "B", "C", "D"]
    out = fetch_prices(tickers, days=30, data_service=ds, max_workers=workers)
    assert list(out) == tickers
    assert ds.peak <= workers
