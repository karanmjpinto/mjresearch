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
        assert (
            "trend" in result
            or "above_sma50" in result
            or isinstance(result.get("macd"), dict)
        )
