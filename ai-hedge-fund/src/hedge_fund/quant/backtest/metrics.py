"""Performance metrics: return, CAGR, Sharpe, Sortino, max drawdown, win rate."""

from __future__ import annotations

import logging
import math

import pandas as pd

logger = logging.getLogger(__name__)


TRADING_DAYS = 252


def compute_metrics(
    equity: pd.Series,
    returns: pd.Series,
    position: pd.Series,
    rf_annual: float = 0.04,
) -> dict:
    """Compute standard performance metrics over the equity curve.

    Parameters
    ----------
    equity : Series of equity values starting at 1.0.
    returns : Series of strategy per-bar returns (already net of position).
    position : Series of positions (0..1) — used to compute time in market.
    rf_annual : Annual risk-free rate for Sharpe. Default 4%.
    """
    if len(equity) < 2:
        return _empty_metrics()

    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    n_days = len(equity)
    years = n_days / TRADING_DAYS
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years > 0 else 0.0

    r = returns.dropna()
    rf_per_bar = (1 + rf_annual) ** (1 / TRADING_DAYS) - 1
    excess = r - rf_per_bar

    vol = r.std() * math.sqrt(TRADING_DAYS) if len(r) > 1 else 0.0
    sharpe = (
        excess.mean() / r.std() * math.sqrt(TRADING_DAYS) if len(r) > 1 and r.std() > 0 else 0.0
    )

    downside = r[r < 0]
    sortino = (
        excess.mean() / downside.std() * math.sqrt(TRADING_DAYS)
        if len(downside) > 1 and downside.std() > 0
        else 0.0
    )

    # Max drawdown
    running_max = equity.cummax()
    dd = (equity - running_max) / running_max
    max_dd = float(dd.min()) if len(dd) else 0.0

    # Calmar: CAGR / |max_dd|
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    # Win rate (per-bar)
    win_rate = float((r > 0).sum()) / len(r) if len(r) else 0.0

    # Time in market
    time_in_market = float(position.mean()) if len(position) else 0.0

    # Number of round-trips (0→1 transitions)
    transitions = (position.diff() > 0).sum()

    return {
        "total_return": _safe(total_return),
        "cagr": _safe(cagr),
        "volatility": _safe(vol),
        "sharpe": _safe(sharpe),
        "sortino": _safe(sortino),
        "max_drawdown": _safe(max_dd),
        "calmar": _safe(calmar),
        "win_rate": _safe(win_rate),
        "time_in_market": _safe(time_in_market),
        "num_trades": int(transitions),
        "n_bars": int(n_days),
        "years": _safe(years),
    }


def _safe(x: float) -> float:
    """Sanitise a computed statistic for the wire.

    NaN and infinity are legitimate outcomes of the formulae above — an
    undefined Sharpe on a flat series, say — and collapse to 0.0 by design. A
    value that will not convert at all is different: it means a caller handed
    this a type the arithmetic never produced, and swallowing that turns a bug
    into a plausible zero sitting in a results table.
    """
    try:
        f = float(x)
    except Exception as exc:
        logger.warning("metric value %r is not numeric (%s); reporting 0.0", x, exc)
        return 0.0
    if math.isnan(f) or math.isinf(f):
        return 0.0
    return round(f, 6)


def _empty_metrics() -> dict:
    return {
        "total_return": 0.0,
        "cagr": 0.0,
        "volatility": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "max_drawdown": 0.0,
        "calmar": 0.0,
        "win_rate": 0.0,
        "time_in_market": 0.0,
        "num_trades": 0,
        "n_bars": 0,
        "years": 0.0,
    }
