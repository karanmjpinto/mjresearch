"""Portfolio-level metrics: expected return, vol, Sharpe, concentration, diversification."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


TRADING_DAYS = 252


def portfolio_metrics(
    weights: np.ndarray,
    returns: pd.DataFrame,
    rf_annual: float = 0.04,
) -> dict:
    """Compute portfolio-level metrics for a given weight vector.

    Includes a backtest of the portfolio over the returns window
    (rebalanced daily — simplification; buy-and-hold would drift).
    """
    if len(returns) < 2:
        return _empty()

    # Per-bar portfolio returns (assuming daily rebalance)
    port_ret = (returns * weights).sum(axis=1)

    mu = port_ret.mean() * TRADING_DAYS
    sigma = port_ret.std() * math.sqrt(TRADING_DAYS)
    rf_per_bar = (1 + rf_annual) ** (1 / TRADING_DAYS) - 1
    sharpe = (
        (port_ret.mean() - rf_per_bar) / port_ret.std() * math.sqrt(TRADING_DAYS)
        if port_ret.std() > 0
        else 0.0
    )

    # Downside volatility
    downside = port_ret[port_ret < 0]
    sortino = (
        (port_ret.mean() - rf_per_bar) / downside.std() * math.sqrt(TRADING_DAYS)
        if len(downside) > 1 and downside.std() > 0
        else 0.0
    )

    # Equity curve + drawdown
    equity = (1 + port_ret).cumprod()
    running_max = equity.cummax()
    dd = (equity - running_max) / running_max
    max_dd = float(dd.min())
    calmar = (mu / abs(max_dd)) if max_dd < 0 else 0.0

    # Concentration — Herfindahl index (1/N = min, 1 = single asset)
    hhi = float((weights**2).sum())
    # Effective N — inverse HHI
    effective_n = 1.0 / hhi if hhi > 0 else 0.0

    # Diversification ratio — weighted avg vol / portfolio vol
    asset_vols = returns.std().values * math.sqrt(TRADING_DAYS)
    weighted_avg_vol = float((weights * asset_vols).sum())
    div_ratio = weighted_avg_vol / sigma if sigma > 0 else 0.0

    # Equity curve for charting (normalized to 1.0)
    curve = []
    for ts, eq in zip(equity.index, equity.values):
        curve.append(
            {
                "date": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts),
                "equity": round(float(eq), 6),
            }
        )

    return {
        "expected_return": _safe(mu),
        "volatility": _safe(sigma),
        "sharpe": _safe(sharpe),
        "sortino": _safe(sortino),
        "max_drawdown": _safe(max_dd),
        "calmar": _safe(calmar),
        "total_return": _safe(equity.iloc[-1] - 1),
        "hhi_concentration": _safe(hhi),
        "effective_n": _safe(effective_n),
        "diversification_ratio": _safe(div_ratio),
        "n_bars": int(len(returns)),
        "equity_curve": curve,
    }


def _safe(x: float) -> float:
    try:
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return round(f, 6)
    except Exception:
        return 0.0


def _empty() -> dict:
    return {
        "expected_return": 0.0,
        "volatility": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "max_drawdown": 0.0,
        "calmar": 0.0,
        "total_return": 0.0,
        "hhi_concentration": 0.0,
        "effective_n": 0.0,
        "diversification_ratio": 0.0,
        "n_bars": 0,
        "equity_curve": [],
    }
