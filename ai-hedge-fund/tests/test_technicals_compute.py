"""Unit tests for shared technical indicator computation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hedge_fund.data.technicals_compute import compute_technicals_from_ohlcv


def test_compute_technicals_from_synthetic_ohlcv():
    n = 250
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.5, 2, n)
    low = close - rng.uniform(0.5, 2, n)
    vol = rng.integers(1_000_000, 10_000_000, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )
    out = compute_technicals_from_ohlcv(df, "TEST", source="test")
    assert out is not None
    assert out["ticker"] == "TEST"
    assert out["source"] == "test"
    assert "rsi_14" in out
    assert "macd" in out
    assert out["macd"]["trend"] in ("bullish", "bearish")
