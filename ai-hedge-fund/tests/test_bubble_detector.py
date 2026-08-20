"""Unit tests for the market-wide bubble detector composite."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hedge_fund.data.bubble_detector import (
    GAUGE_SPECS,
    REQUIRED_SERIES,
    compute_bubble_detector,
)


def _fred_frame(values: np.ndarray, name: str, freq: str = "D") -> pd.DataFrame:
    idx = pd.date_range("2015-01-01", periods=len(values), freq=freq)
    return pd.DataFrame({name: values}, index=idx)


def _synthetic_fred(n: int = 500, seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    out: dict[str, pd.DataFrame] = {}
    for sid in REQUIRED_SERIES:
        base = 100 + np.cumsum(rng.normal(0, 1, n))
        out[sid] = _fred_frame(np.abs(base) + 1.0, sid)
    return out


def test_compute_bubble_detector_full():
    out = compute_bubble_detector(_synthetic_fred())
    assert "error" not in out
    assert out["source"] == "FRED"
    assert 0 <= out["composite_score"] <= 100
    assert out["composite_status"] in ("minimal", "low", "moderate", "elevated", "extreme")
    assert len(out["gauges"]) == len(GAUGE_SPECS)
    for g in out["gauges"]:
        assert 0 <= g["risk_score"] <= 100
        assert g["direction"] in ("high", "low")


def test_missing_series_are_skipped():
    fred = _synthetic_fred()
    # Drop VIX entirely; its gauge should be reported missing, not crash.
    fred["VIXCLS"] = None
    out = compute_bubble_detector(fred)
    assert "vix" in out["missing_gauges"]
    assert all(g["id"] != "vix" for g in out["gauges"])


def test_no_data_returns_error():
    out = compute_bubble_detector({sid: None for sid in REQUIRED_SERIES})
    assert "error" in out


def test_direction_scoring():
    # A "high" gauge at its all-time max should score near 100; a "low" gauge
    # (VIX) at its max should score near 0 (high VIX = fear, not complacency).
    n = 300
    rising = np.linspace(1, 100, n)
    fred = {sid: _fred_frame(rising, sid) for sid in REQUIRED_SERIES}
    out = compute_bubble_detector(fred)
    by_id = {g["id"]: g for g in out["gauges"]}
    assert by_id["vix"]["risk_score"] < 10
    assert by_id["yield_curve"]["risk_score"] < 10
