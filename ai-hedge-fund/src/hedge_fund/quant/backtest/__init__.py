"""Rule-based backtesting: signals over a historical price series.

Vectorized using pandas/numpy. Designed to be swapped for VectorBT later
if strategy library grows beyond what we can maintain here.
"""

from hedge_fund.quant.backtest.engine import BacktestResult, run_backtest
from hedge_fund.quant.backtest.metrics import compute_metrics
from hedge_fund.quant.backtest.strategies import (
    STRATEGY_REGISTRY,
    STRATEGY_META,
    Strategy,
    get_strategy,
)

__all__ = [
    "BacktestResult",
    "run_backtest",
    "compute_metrics",
    "STRATEGY_REGISTRY",
    "STRATEGY_META",
    "Strategy",
    "get_strategy",
]
