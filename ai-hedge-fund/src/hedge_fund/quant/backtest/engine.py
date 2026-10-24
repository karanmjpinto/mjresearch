"""Vectorized backtest engine — apply strategy signal to price series.

No look-ahead bias: position on day t is determined by signal on day t-1.
Transaction costs applied as a flat per-trade percentage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from hedge_fund.data.frames import normalise_prices
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
    verdict: dict = field(default_factory=dict)  # see split_verdict

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
            "verdict": self.verdict,
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
    verdict = split_verdict(equity, net_ret, position, benchmark, bar_ret, rf_annual)

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
        verdict=verdict,
    )


def split_verdict(
    equity: pd.Series,
    net_ret: pd.Series,
    position: pd.Series,
    benchmark: pd.Series,
    bar_ret: pd.Series,
    rf_annual: float,
) -> dict:
    """Does the strategy beat buy-and-hold in both halves of the window, not just overall?

    A whole-window win can be one lucky stretch. Splitting the window in two and
    asking for the win in each is the cheapest test of that. The rules here use
    fixed published parameters, not ones fitted to this data, so neither half is
    "held out" in the fitting sense — this is a stability check, not an
    out-of-sample one.

    Two measures, growth (CAGR) and risk-adjusted return (Sharpe). A measure
    counts only if the strategy wins on it in both halves:
      - "holds"      both measures hold up in both halves
      - "trade_off"  one does
      - "no_edge"    neither does
    """
    mid = len(equity) // 2
    halves = []
    for sl in (slice(None, mid), slice(mid, None)):
        s = compute_metrics(equity[sl], net_ret[sl], position[sl], rf_annual=rf_annual)
        b = compute_metrics(
            benchmark[sl], bar_ret[sl], pd.Series(1.0, index=bar_ret[sl].index), rf_annual=rf_annual
        )
        halves.append(
            {
                "start_date": str(equity.index[sl][0])[:10],
                "end_date": str(equity.index[sl][-1])[:10],
                "cagr": s["cagr"],
                "benchmark_cagr": b["cagr"],
                "sharpe": s["sharpe"],
                "benchmark_sharpe": b["sharpe"],
            }
        )
    cagr_holds = all(h["cagr"] > h["benchmark_cagr"] for h in halves)
    sharpe_holds = all(h["sharpe"] > h["benchmark_sharpe"] for h in halves)
    label = {2: "holds", 1: "trade_off", 0: "no_edge"}[cagr_holds + sharpe_holds]
    return {
        "label": label,
        "cagr_holds": cagr_holds,
        "sharpe_holds": sharpe_holds,
        "halves": halves,
    }


def _prepare_prices(df: pd.DataFrame) -> pd.DataFrame:
    """A dated, numeric price frame, or a refusal the caller can read.

    The shaping lives in `hedge_fund.data.frames`, shared with the other price
    consumers. This wrapper adds only the engine's own policy: a frame with no
    readable close is a programming error here, not an empty backtest.
    """
    prepared = normalise_prices(df)
    if prepared is None:
        raise ValueError("DataFrame missing 'close' column after normalization.")
    return prepared


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
