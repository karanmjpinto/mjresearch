"""Tests for the data platform."""

from __future__ import annotations

import importlib.util

import pandas as pd
import pytest

from hedge_fund.data.bist import is_bist_ticker, strip_bist_suffix
from hedge_fund.data.cache import DataCategory
from hedge_fund.data.nordic import get_nordic_context, is_nordic_ticker, validate_nordic_ticker
from hedge_fund.data.registry import ProviderRegistry
from hedge_fund.data.service import DataService


def _openbb_installed() -> bool:
    return importlib.util.find_spec("openbb") is not None


# ------------------------------------------------------------------
# Unit tests (no network)
# ------------------------------------------------------------------


class TestOpenBBChainOrder:
    def test_price_chain_openbb_first(self):
        reg = ProviderRegistry()
        chain = reg.get_chain(DataCategory.PRICE)
        assert chain, "expected at least one price provider"
        assert chain[0] == "openbb", f"got {chain}"

    def test_fundamentals_chain_openbb_first(self):
        reg = ProviderRegistry()
        chain = reg.get_chain(DataCategory.FUNDAMENTALS)
        assert chain[0] == "openbb"


class TestBistHelpers:
    def test_is_bist(self):
        assert is_bist_ticker("THYAO.IS")
        assert is_bist_ticker("EREGL.IS")
        assert not is_bist_ticker("AAPL")
        assert not is_bist_ticker("NOVO-B.CO")

    def test_strip_suffix(self):
        assert strip_bist_suffix("THYAO.IS") == "THYAO"
        assert strip_bist_suffix("AAPL") == "AAPL"


class TestNordicHelpers:
    def test_is_nordic(self):
        assert is_nordic_ticker("NOVO-B.CO")
        assert is_nordic_ticker("VOLV-B.ST")
        assert is_nordic_ticker("NESTE.HE")
        assert not is_nordic_ticker("AAPL")
        assert not is_nordic_ticker("THYAO.IS")

    def test_context(self):
        ctx = get_nordic_context("NOVO-B.CO")
        assert ctx is not None
        assert ctx["currency"] == "DKK"
        assert ctx["country"] == "Denmark"

    def test_validate(self):
        assert validate_nordic_ticker("NOVO-B.CO")
        assert validate_nordic_ticker("VOLV-B.ST")
        assert not validate_nordic_ticker("AAPL")
        assert not validate_nordic_ticker(".ST")  # too short


# ------------------------------------------------------------------
# Integration tests (require network)
# ------------------------------------------------------------------


@pytest.mark.skipif(not _openbb_installed(), reason="openbb not installed")
class TestDataServiceIntegration:
    ds = DataService()

    def test_price_history(self):
        df = self.ds.get_price_history("AAPL", days=30)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert "close" in df.columns

    def test_fundamentals(self):
        result = self.ds.get_fundamentals("AAPL")
        assert "ticker" in result
        assert result["ticker"] == "AAPL"

    def test_technicals(self):
        result = self.ds.get_technical_indicators("AAPL")
        assert "rsi_14" in result
        assert "macd" in result
        # Provider-dependent: top-level trend vs SMA flags vs MACD subdict
        assert "trend" in result or "above_sma50" in result or isinstance(result.get("macd"), dict)


# ------------------------------------------------------------------
# Merging complementary providers
# ------------------------------------------------------------------


def test_merge_fields_fills_gaps_without_overwriting_earlier_providers():
    """Chain order still decides; only the blanks get filled.

    This is the bug it exists for: the first provider answered for fundamentals
    with market data and a null for every income-statement line, so a valuation
    could not be computed from a payload that looked populated.
    """
    from hedge_fund.data.registry import merge_fields

    merged, sources = merge_fields(
        [
            ("openbb", {"market_cap": 100, "revenue": None, "beta": 1.1}),
            ("yfinance", {"market_cap": 999, "revenue": 416, "ebitda": 130}),
        ]
    )
    assert merged["market_cap"] == 100  # the earlier provider is not overwritten
    assert merged["revenue"] == 416  # the blank is filled
    assert merged["ebitda"] == 130  # and a field the first one never had
    assert sources == {
        "market_cap": "openbb",
        "beta": "openbb",
        "revenue": "yfinance",
        "ebitda": "yfinance",
    }


def test_merge_fields_records_who_supplied_each_number():
    from hedge_fund.data.registry import merge_fields

    _, sources = merge_fields([("a", {"x": 1}), ("b", {"y": 2})])
    assert sources["x"] == "a" and sources["y"] == "b"


def test_merge_fields_ignores_nulls_and_non_dicts():
    from hedge_fund.data.registry import merge_fields

    merged, _ = merge_fields([("a", {"x": None}), ("b", None), ("c", {"x": 5})])  # type: ignore[list-item]
    assert merged == {"x": 5}


def test_merge_fields_on_nothing_is_empty_not_an_error():
    from hedge_fund.data.registry import merge_fields

    assert merge_fields([]) == ({}, {})


# ------------------------------------------------------------------
# Sector performance — the shape has to survive the round trip
#
# This panel was dead and looked merely "unavailable". Two separate faults:
# the model called the first field `real_time` while the provider, the API
# fallback and the frontend all say `realtime`, and the model typed every
# period as a mapping while the provider sends ranked rows. Pydantic dropped
# the unknown key, rejected the rows, and the whole object became None.
# ------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def get(self, *args: object, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(self._payload)


def _sector_provider(monkeypatch, payload: dict):
    import httpx

    from hedge_fund.data.providers import alpha_vantage_provider as mod

    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "Client", lambda **kw: _FakeClient(payload))
    return mod.AlphaVantageProvider()._sector_performance()


def test_sector_ranks_survive_the_model(monkeypatch):
    """The regression: a well-formed response used to fail validation."""
    out = _sector_provider(
        monkeypatch,
        {
            "Rank A: Real-Time Performance": {"Technology": "1.42%", "Energy": "-0.31%"},
            "Rank B: 1 Day Performance": {"Technology": "0.90%"},
        },
    )
    assert out is not None, "a valid response must not be swallowed"
    assert [r.sector for r in out.realtime] == ["Technology", "Energy"]
    assert out.realtime[0].change_pct == 1.42
    assert out.realtime[1].change_pct == -0.31
    assert out.one_day[0].sector == "Technology"


def test_sector_rank_order_is_preserved(monkeypatch):
    """The order is the information — these arrive ranked best to worst."""
    out = _sector_provider(
        monkeypatch,
        {"Rank A: Real-Time Performance": {"A": "3%", "B": "2%", "C": "-1%"}},
    )
    assert [r.sector for r in out.realtime] == ["A", "B", "C"]


def test_a_retired_endpoint_is_unavailable_not_a_flat_market(monkeypatch):
    """Alpha Vantage now answers `{}` here. Zero sectors, not zero movement."""
    assert _sector_provider(monkeypatch, {}) is None


def test_a_rate_limit_notice_is_still_unavailable(monkeypatch):
    assert _sector_provider(monkeypatch, {"Note": "call frequency"}) is None
