"""Vectorized backtest engine — apply strategy signal to price series.

No look-ahead bias: position on day t is determined by signal on day t-1.
Transaction costs applied as a flat per-trade percentage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from hedge_fund.quant.backtest.metrics import compute_metrics
from hedge_fund.quant.backtest.strategies import (
    STRATEGY_META,
    Strategy,
    get_strategy,
)


@dataclass
class BacktestResult:
    ticker: str
    strategy_id: str
    strategy_name: str
    strategy_description: str
    params: dict
    start_date: str
    end_date: str
    equity_curve: list[dict]  # [{date, equity, benchmark, position}]
    metrics: dict  # strategy metrics
    benchmark_metrics: dict  # buy-and-hold metrics (same window)
    trades: list[dict] = field(default_factory=list)  # entry/exit log

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "strategy_description": self.strategy_description,
            "params": self.params,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "equity_curve": self.equity_curve,
            "metrics": self.metrics,
            "benchmark_metrics": self.benchmark_metrics,
            "trades": self.trades,
        }


def run_backtest(
    df: pd.DataFrame,
    ticker: str,
    strategy_id: str,
    params: dict | None = None,
    fee_pct: float = 0.0005,  # 5 bps per side
    rf_annual: float = 0.04,
) -> BacktestResult:
    """Run a strategy backtest over a price DataFrame.

    Parameters
    ----------
    df : DataFrame with at least a 'close' column, date-indexed or 'date' column.
    ticker : Symbol for labeling.
    strategy_id : Key in STRATEGY_REGISTRY.
    params : Override strategy default params.
    fee_pct : One-way transaction cost (applied at each position change).
    rf_annual : Risk-free rate for Sharpe.
    """
    meta = STRATEGY_META[strategy_id]
    resolved_params = {**meta.default_params, **(params or {})}

    df = _prepare_prices(df)
    if len(df) < 20:
        raise ValueError(f"Not enough price data ({len(df)} bars) for a meaningful backtest.")

    strategy: Strategy = get_strategy(strategy_id)
    signal = strategy(df, resolved_params).astype(float).clip(0, 1)

    # Apply one-bar lag to avoid look-ahead bias
    position = signal.shift(1).fillna(0)

    # Per-bar returns
    bar_ret = df["close"].pct_change().fillna(0)

    # Strategy return before fees: position * bar_ret
    strat_ret = position * bar_ret

    # Transaction costs: |delta position| * fee
    pos_change = position.diff().abs().fillna(position.iloc[0])
    costs = pos_change * fee_pct
    net_ret = strat_ret - costs

    # Equity curves normalized to 1.0
    equity = (1 + net_ret).cumprod()
    benchmark = (1 + bar_ret).cumprod()

    # Pack
    curve = []
    for ts, eq, bm, pos in zip(df.index, equity.values, benchmark.values, position.values):
        curve.append(
            {
                "date": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts),
                "equity": round(float(eq), 6),
                "benchmark": round(float(bm), 6),
                "position": round(float(pos), 3),
            }
        )

    metrics = compute_metrics(equity, net_ret, position, rf_annual=rf_annual)
    benchmark_metrics = compute_metrics(
        benchmark, bar_ret, pd.Series(1.0, index=df.index), rf_annual=rf_annual
    )

    trades = _extract_trades(df, position)

    return BacktestResult(
        ticker=ticker,
        strategy_id=strategy_id,
        strategy_name=meta.name,
        strategy_description=meta.description,
        params=resolved_params,
        start_date=str(df.index[0].date()) if hasattr(df.index[0], "date") else str(df.index[0]),
        end_date=str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
        equity_curve=curve,
        metrics=metrics,
        benchmark_metrics=benchmark_metrics,
        trades=trades,
    )


def _prepare_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure df has 'close' column and a DateTimeIndex."""
    df = df.copy()
    # Normalize column names to lowercase
    df.columns = [str(c).lower() for c in df.columns]

    # If there's no 'close' but there's 'adj close' / 'adjclose', use that
    if "close" not in df.columns:
        for alt in ("adjclose", "adj close", "adjusted_close", "price"):
            if alt in df.columns:
                df = df.rename(columns={alt: "close"})
                break

    if "close" not in df.columns:
        raise ValueError("DataFrame missing 'close' column after normalization.")

    # Handle date column
    if "date" in df.columns:
        df = df.set_index(pd.to_datetime(df["date"])).drop(columns=["date"])
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    df = df.sort_index()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    return df


def _extract_trades(df: pd.DataFrame, position: pd.Series) -> list[dict]:
    """Extract round-trip trades from position series (0→1 = entry, 1→0 = exit)."""
    trades: list[dict] = []
    entry_date = None
    entry_price = None
    prev = 0.0
    for ts, pos in zip(df.index, position.values):
        price = float(df["close"].loc[ts])
        if prev == 0 and pos > 0:  # entry
            entry_date = ts
            entry_price = price
        elif prev > 0 and pos == 0 and entry_date is not None:  # exit
            ret = (price / entry_price) - 1 if entry_price else 0.0
            trades.append(
                {
                    "entry_date": entry_date.strftime("%Y-%m-%d"),
                    "entry_price": round(entry_price, 2),
                    "exit_date": ts.strftime("%Y-%m-%d"),
                    "exit_price": round(price, 2),
                    "return_pct": round(ret * 100, 2),
                    "days_held": (ts - entry_date).days,
                }
            )
            entry_date = None
            entry_price = None
        prev = pos

    # Open trade at end of series
    if entry_date is not None and entry_price is not None:
        last_price = float(df["close"].iloc[-1])
        ret = (last_price / entry_price) - 1
        trades.append(
            {
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "entry_price": round(entry_price, 2),
                "exit_date": "(open)",
                "exit_price": round(last_price, 2),
                "return_pct": round(ret * 100, 2),
                "days_held": (df.index[-1] - entry_date).days,
            }
        )

    return trades
