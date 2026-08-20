"""Portfolio construction — conviction-weighted, mean-variance, HRP.

All methods accept a covariance matrix / return matrix of shape (T, N)
and produce a weight vector of length N that sums to 1.0.
"""

from hedge_fund.quant.portfolio.metrics import portfolio_metrics
from hedge_fund.quant.portfolio.weights import (
    METHOD_META,
    METHOD_REGISTRY,
    MethodMeta,
    optimize_weights,
)

__all__ = [
    "METHOD_META",
    "METHOD_REGISTRY",
    "MethodMeta",
    "optimize_weights",
    "portfolio_metrics",
]
