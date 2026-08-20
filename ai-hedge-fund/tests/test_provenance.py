"""Provider provenance, cache-key correctness, and series verification."""

from __future__ import annotations

import pandas as pd
import pytest

from hedge_fund.data.cache import CachedValue, DataCategory, TTLCache
from hedge_fund.data.provenance import (
    capture,
    verify_mapping,
    verify_price_frame,
    verify_sequence,
)
from hedge_fund.data.rate_limiter import RateLimiter
from hedge_fund.data.registry import ProviderRegistry


class _FakeProvider:
    """Records the kwargs it was asked for so tests can assert on cache behaviour."""

    def __init__(self, name: str, payload=None, fail: bool = False) -> None:
        self.name = name
        self.priority = 1
        self.payload = payload
        self.fail = fail
        self.calls: list[dict] = []

    def fetch(self, category, key, **kwargs):
        self.calls.append({"key": key, **kwargs})
        if self.fail:
            raise RuntimeError("provider exploded")
        if callable(self.payload):
            return self.payload(key, **kwargs)
        return self.payload


def _registry(*providers) -> ProviderRegistry:
    """A registry with the given providers wired to every category, no autodiscovery."""
    reg = ProviderRegistry.__new__(ProviderRegistry)
    reg.cache = TTLCache()
    reg.limiter = RateLimiter()
    reg._providers = list(providers)
    reg._config = {}
    reg._chains = {cat: list(providers) for cat in DataCategory}
    return reg


def _frame(days: int) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=days, freq="D")
    return pd.DataFrame({"close": range(1, days + 1)}, index=idx)


# ----------------------------------------------------------------------
# Cache key correctness
# ----------------------------------------------------------------------


def test_differing_days_do_not_share_a_cache_entry():
    """A 365-day fetch must not satisfy a later 30-day request."""
    p = _FakeProvider("fake", payload=lambda key, **kw: _frame(kw["days"]))
    reg = _registry(p)

    long_frame = reg.get(DataCategory.PRICE, "AAPL", days=365)
    short_frame = reg.get(DataCategory.PRICE, "AAPL", days=30)

    assert len(long_frame) == 365
    assert len(short_frame) == 30, "30-day request was served the 365-day frame"
    assert len(p.calls) == 2


def test_differing_limits_do_not_share_a_cache_entry():
    p = _FakeProvider("fake", payload=lambda key, **kw: [{"i": i} for i in range(kw["limit"])])
    reg = _registry(p)

    assert len(reg.get(DataCategory.NEWS, "AAPL", limit=10)) == 10
    assert len(reg.get(DataCategory.NEWS, "AAPL", limit=5)) == 5


def test_identical_params_do_hit_cache():
    p = _FakeProvider("fake", payload=lambda key, **kw: _frame(kw["days"]))
    reg = _registry(p)

    reg.get(DataCategory.PRICE, "AAPL", days=30)
    reg.get(DataCategory.PRICE, "AAPL", days=30)
    assert len(p.calls) == 1, "second identical request should be served from cache"


def test_none_valued_params_are_ignored_in_key():
    assert ProviderRegistry._cache_key("AAPL", {"days": 30, "end_date": None}) == "AAPL|days=30"
    assert ProviderRegistry._cache_key("AAPL", {}) == "AAPL"


# ----------------------------------------------------------------------
# Provenance
# ----------------------------------------------------------------------


def test_provenance_records_which_provider_answered():
    p = _FakeProvider("primary", payload={"pe_ratio": 18.0, "currency": "USD"})
    reg = _registry(p)

    with capture() as log:
        reg.get(DataCategory.FUNDAMENTALS, "AAPL")

    assert log.providers_used() == ["primary"]
    slot = log.by_slot()["fundamentals:AAPL"]
    assert slot["provider"] == "primary"
    assert slot["from_cache"] is False
    assert slot["fetched_at"]


def test_provenance_survives_a_cache_hit():
    """A cache hit must still name its original source, not report 'unknown'."""
    p = _FakeProvider("primary", payload={"pe_ratio": 18.0, "currency": "USD"})
    reg = _registry(p)
    reg.get(DataCategory.FUNDAMENTALS, "AAPL")

    with capture() as log:
        reg.get(DataCategory.FUNDAMENTALS, "AAPL")

    slot = log.by_slot()["fundamentals:AAPL"]
    assert slot["provider"] == "primary"
    assert slot["from_cache"] is True
    assert slot["age_seconds"] is not None


def test_provenance_records_fallback_to_second_provider():
    broken = _FakeProvider("broken", fail=True)
    backup = _FakeProvider("backup", payload={"pe_ratio": 21.0, "currency": "USD"})
    reg = _registry(broken, backup)

    with capture() as log:
        reg.get(DataCategory.FUNDAMENTALS, "AAPL")

    slot = log.by_slot()["fundamentals:AAPL"]
    assert slot["provider"] == "backup"
    assert "broken:error" in slot["attempted"]


def test_provenance_records_total_failure():
    reg = _registry(_FakeProvider("broken", fail=True))

    with capture() as log:
        value = reg.get(DataCategory.FUNDAMENTALS, "AAPL")

    assert value is None
    assert log.warnings(), "a total failure should surface a warning"


def test_capture_is_scoped_and_nestable():
    p = _FakeProvider("primary", payload={"a": 1})
    reg = _registry(p)

    reg.get(DataCategory.ESG, "OUTSIDE")  # no active log — must not raise
    with capture() as log:
        reg.get(DataCategory.ESG, "INSIDE")
    assert len(log) == 1

    reg.get(DataCategory.ESG, "AFTER")  # log is detached again
    assert len(log) == 1


@pytest.mark.asyncio
async def test_provenance_spans_async_fanout():
    """Concurrent persona-style fan-out shares one log."""
    import asyncio

    p = _FakeProvider("primary", payload={"a": 1})
    reg = _registry(p)

    async def fetch(t):
        return reg.get(DataCategory.ESG, t)

    with capture() as log:
        await asyncio.gather(*(fetch(t) for t in ("A", "B", "C")))

    assert len(log) == 3


def test_legacy_cache_entry_without_envelope_is_tolerated():
    reg = _registry(_FakeProvider("primary", payload={"a": 1}))
    reg.cache.set(DataCategory.ESG, "AAPL", {"raw": "legacy"})

    with capture() as log:
        value = reg.get(DataCategory.ESG, "AAPL")

    assert value == {"raw": "legacy"}
    assert log.by_slot()["esg:AAPL"]["from_cache"] is True


def test_cached_value_envelope_roundtrip():
    cache = TTLCache()
    cache.set(DataCategory.PRICE, "K", CachedValue(value=42, provider="p", fetched_at="t"))
    got = cache.get(DataCategory.PRICE, "K")
    assert got.value == 42 and got.provider == "p"


# ----------------------------------------------------------------------
# Verification
# ----------------------------------------------------------------------


def test_verify_price_frame_happy_path():
    checks = verify_price_frame(_frame(60), expected_days=60)
    assert checks.row_count == 60
    assert checks.frequency == "daily"
    assert checks.warnings == []


def test_verify_price_frame_flags_short_window():
    checks = verify_price_frame(_frame(3), expected_days=365)
    assert any("rows for a 365-day window" in w for w in checks.warnings)


def test_verify_price_frame_flags_unadjusted_close():
    df = _frame(10)
    df["adj_close"] = range(10)
    checks = verify_price_frame(df)
    assert checks.adjusted is False
    assert any("unadjusted" in w for w in checks.warnings)


def test_verify_price_frame_flags_gaps():
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-03-01", "2024-03-02"])
    checks = verify_price_frame(pd.DataFrame({"close": [1, 2, 3, 4, 5]}, index=idx))
    assert any("gap of" in w for w in checks.warnings)


def test_verify_price_frame_flags_empty():
    checks = verify_price_frame(pd.DataFrame())
    assert checks.row_count == 0
    assert "empty price frame" in checks.warnings


def test_verify_mapping_flags_missing_currency():
    checks = verify_mapping({"market_cap": 1_000_000}, category="fundamentals")
    assert any("currency not declared" in w for w in checks.warnings)


def test_verify_mapping_accepts_declared_currency():
    checks = verify_mapping({"market_cap": 1_000_000, "currency": "try"}, category="fundamentals")
    assert checks.currency == "TRY"
    assert checks.warnings == []


def test_verify_mapping_ignores_ratio_only_payloads():
    checks = verify_mapping({"pe_ratio": 18.0, "beta": 1.1}, category="fundamentals")
    assert checks.warnings == []


def test_verify_mapping_surfaces_provider_error():
    checks = verify_mapping({"error": "no data"}, category="fundamentals")
    assert any("no data" in w for w in checks.warnings)


def test_verify_sequence():
    assert verify_sequence([{"a": 1}]).row_count == 1
    assert "empty list" in verify_sequence([]).warnings
