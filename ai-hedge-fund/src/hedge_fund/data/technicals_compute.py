"""Shared OHLCV → technical indicator dict (used by OpenBB and yfinance providers)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _safe_float(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_round(val: Any, decimals: int = 2) -> float | None:
    f = _safe_float(val)
    return round(f, decimals) if f is not None else None


def compute_technicals_from_ohlcv(
    df: pd.DataFrame | None,
    ticker: str,
    source: str = "yfinance",
) -> dict | None:
    """Compute RSI, MACD, Bollinger, SMAs, ATR from a lowercase OHLCV frame (DatetimeIndex)."""
    if df is None or df.empty:
        return None
    if not all(c in df.columns for c in ("close", "high", "low", "volume")):
        return None

    close = df["close"]

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    macd_hist = macd_line - signal_line

    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20

    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    high = df["high"]
    low = df["low"]
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean()

    latest = close.iloc[-1]
    return {
        "ticker": ticker,
        "price": float(latest),
        "rsi_14": _safe_round(rsi.iloc[-1]),
        "macd": {
            "line": _safe_round(macd_line.iloc[-1]),
            "signal": _safe_round(signal_line.iloc[-1]),
            "histogram": _safe_round(macd_hist.iloc[-1]),
            "trend": "bullish" if macd_hist.iloc[-1] > 0 else "bearish",
        },
        "bollinger": {
            "upper": _safe_round(bb_upper.iloc[-1]),
            "middle": _safe_round(sma20.iloc[-1]),
            "lower": _safe_round(bb_lower.iloc[-1]),
            "width": _safe_round((bb_upper.iloc[-1] - bb_lower.iloc[-1]) / sma20.iloc[-1] * 100),
        },
        "sma_50": _safe_round(sma50.iloc[-1]),
        "sma_200": _safe_round(sma200.iloc[-1]),
        "atr_14": _safe_round(atr.iloc[-1]),
        "above_sma50": bool(latest > sma50.iloc[-1]) if pd.notna(sma50.iloc[-1]) else None,
        "above_sma200": bool(latest > sma200.iloc[-1]) if pd.notna(sma200.iloc[-1]) else None,
        "volume_avg_20": _safe_round(df["volume"].rolling(20).mean().iloc[-1], 0),
        "source": source,
    }
