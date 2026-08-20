"""Strategy definitions — each maps OHLCV → position series (0 = flat, 1 = long).

Strategies are pure functions over a DataFrame of OHLCV. No look-ahead bias:
signals computed on day t determine position on day t+1 (handled in engine).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

# A strategy: (DataFrame, params) -> signal series (float, 0..1)
Strategy = Callable[[pd.DataFrame, dict], pd.Series]


@dataclass(frozen=True)
class StrategyMeta:
    id: str
    name: str
    description: str
    default_params: dict
    category: str  # "trend" | "mean_reversion" | "volatility" | "benchmark"


# ------------------------------------------------------------------------
# Individual strategies
# ------------------------------------------------------------------------


def _buy_and_hold(df: pd.DataFrame, _params: dict) -> pd.Series:
    """Benchmark: always long."""
    return pd.Series(1.0, index=df.index)


def _golden_cross(df: pd.DataFrame, params: dict) -> pd.Series:
    """Classic trend-following: long when fast SMA > slow SMA."""
    fast = int(params.get("fast", 50))
    slow = int(params.get("slow", 200))
    sma_f = df["close"].rolling(fast).mean()
    sma_s = df["close"].rolling(slow).mean()
    return (sma_f > sma_s).astype(float)


def _rsi_reversion(df: pd.DataFrame, params: dict) -> pd.Series:
    """Mean reversion: enter long when RSI crosses below buy_threshold,
    exit when RSI crosses above sell_threshold. Stays flat between."""
    period = int(params.get("period", 14))
    buy_th = float(params.get("buy_threshold", 30))
    sell_th = float(params.get("sell_threshold", 70))

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # State machine: 1 when RSI last crossed below buy_th, 0 after crossing above sell_th
    pos = np.zeros(len(df))
    state = 0
    for i, val in enumerate(rsi.values):
        if np.isnan(val):
            pos[i] = 0
            continue
        if state == 0 and val < buy_th:
            state = 1
        elif state == 1 and val > sell_th:
            state = 0
        pos[i] = state
    return pd.Series(pos, index=df.index)


def _bollinger_breakout(df: pd.DataFrame, params: dict) -> pd.Series:
    """Volatility breakout: long when close breaks above upper Bollinger band.
    Exit when close touches middle band (mean reversion exit)."""
    period = int(params.get("period", 20))
    stds = float(params.get("stds", 2.0))

    mid = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    upper = mid + stds * std

    pos = np.zeros(len(df))
    state = 0
    for i in range(len(df)):
        c = df["close"].iloc[i]
        u = upper.iloc[i]
        m = mid.iloc[i]
        if np.isnan(u) or np.isnan(m):
            pos[i] = 0
            continue
        if state == 0 and c > u:
            state = 1
        elif state == 1 and c < m:
            state = 0
        pos[i] = state
    return pd.Series(pos, index=df.index)


def _trend_and_drawdown(df: pd.DataFrame, params: dict) -> pd.Series:
    """Contrarian-within-trend: long when price is above SMA200 AND
    pulled back 10%+ from 60-day high (catch trend pullbacks)."""
    trend_sma = int(params.get("trend_sma", 200))
    lookback = int(params.get("lookback", 60))
    drawdown = float(params.get("drawdown", 0.10))

    sma = df["close"].rolling(trend_sma).mean()
    hi = df["close"].rolling(lookback).max()
    dd = (df["close"] - hi) / hi

    in_trend = df["close"] > sma
    pulled_back = dd < -drawdown

    # Stay long while in uptrend; (re-enter each qualifying pullback)
    signal = (in_trend & pulled_back).astype(float)
    # Carry forward while still in trend
    pos = np.zeros(len(df))
    state = 0
    for i in range(len(df)):
        if not in_trend.iloc[i]:
            state = 0
        elif signal.iloc[i]:
            state = 1
        # else keep state
        pos[i] = state
    return pd.Series(pos, index=df.index)


def _momentum(df: pd.DataFrame, params: dict) -> pd.Series:
    """Momentum: long when trailing 6-month return > 0."""
    lookback = int(params.get("lookback", 126))  # ~6 months trading days
    mom = df["close"].pct_change(lookback)
    return (mom > 0).fillna(0).astype(float)


# ------------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------------


STRATEGY_REGISTRY: dict[str, Strategy] = {
    "buy_and_hold": _buy_and_hold,
    "golden_cross": _golden_cross,
    "rsi_reversion": _rsi_reversion,
    "bollinger_breakout": _bollinger_breakout,
    "trend_and_drawdown": _trend_and_drawdown,
    "momentum": _momentum,
}


STRATEGY_META: dict[str, StrategyMeta] = {
    "buy_and_hold": StrategyMeta(
        id="buy_and_hold",
        name="Buy & Hold",
        description="Baseline: always long. The benchmark every other strategy must beat.",
        default_params={},
        category="benchmark",
    ),
    "golden_cross": StrategyMeta(
        id="golden_cross",
        name="Golden Cross (50/200)",
        description="Long when 50-day SMA is above 200-day SMA. Classic trend-following.",
        default_params={"fast": 50, "slow": 200},
        category="trend",
    ),
    "rsi_reversion": StrategyMeta(
        id="rsi_reversion",
        name="RSI Mean Reversion (14)",
        description="Buy when RSI-14 drops below 30 (oversold). Sell when it rises above 70.",
        default_params={"period": 14, "buy_threshold": 30, "sell_threshold": 70},
        category="mean_reversion",
    ),
    "bollinger_breakout": StrategyMeta(
        id="bollinger_breakout",
        name="Bollinger Breakout",
        description="Long on close above upper band (20-day, 2σ). Exit on mean-revert to middle band.",
        default_params={"period": 20, "stds": 2.0},
        category="volatility",
    ),
    "trend_and_drawdown": StrategyMeta(
        id="trend_and_drawdown",
        name="Buy the Dip in Uptrend",
        description="Long in uptrend (>SMA200) after 10%+ pullback from 60d high. Exit when trend breaks.",
        default_params={"trend_sma": 200, "lookback": 60, "drawdown": 0.10},
        category="trend",
    ),
    "momentum": StrategyMeta(
        id="momentum",
        name="6-Month Momentum",
        description="Long when trailing 6-month return is positive. Jegadeesh-Titman style.",
        default_params={"lookback": 126},
        category="trend",
    ),
}


def get_strategy(strategy_id: str) -> Strategy:
    if strategy_id not in STRATEGY_REGISTRY:
        raise KeyError(f"Unknown strategy '{strategy_id}'. Available: {sorted(STRATEGY_REGISTRY)}")
    return STRATEGY_REGISTRY[strategy_id]
