"""Portfolio weighting methods.

Methods
-------
- equal_weight: 1/N across the basket (baseline)
- conviction_weighted: weight ∝ AI conviction score (BUY filter applied)
- mean_variance: Classical Markowitz max-Sharpe with long-only, sum=1
- hrp: Hierarchical Risk Parity (Lopez de Prado 2016)
- risk_parity: Inverse-vol, equal risk contribution (simple)

Input: returns DataFrame shape (T, N) with assets as columns.
Output: np.ndarray of weights summing to 1.0, length N.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MethodMeta:
    id: str
    name: str
    description: str
    uses_conviction: bool
    uses_returns: bool
    category: str  # "baseline" | "signal" | "optimization" | "risk"


# ------------------------------------------------------------------------
# Methods
# ------------------------------------------------------------------------


def _equal_weight(returns: pd.DataFrame, convictions: dict[str, float] | None = None) -> np.ndarray:  # noqa: ARG001
    n = len(returns.columns)
    return np.full(n, 1.0 / n)


def _conviction_weighted(
    returns: pd.DataFrame, convictions: dict[str, float] | None = None
) -> np.ndarray:
    """Weight proportional to conviction score. Missing/zero → 50 default.

    Filter: only positive-conviction names get weight (BUY-side by design).
    If no convictions supplied, falls back to equal weight.
    """
    tickers = list(returns.columns)
    if not convictions:
        return _equal_weight(returns)

    raw = np.array([float(convictions.get(t, 50.0)) for t in tickers])
    # Zero out negative/low convictions (<40 treated as HOLD/neutral)
    raw = np.where(raw < 40, 0.0, raw)
    total = raw.sum()
    if total == 0:
        return _equal_weight(returns)
    return raw / total


def _inverse_vol(returns: pd.DataFrame, convictions: dict[str, float] | None = None) -> np.ndarray:  # noqa: ARG001
    """Simple risk parity: w ∝ 1/vol."""
    vol = returns.std().values
    vol = np.where(vol <= 0, np.nan, vol)
    inv = 1.0 / vol
    if np.isnan(inv).all():
        return _equal_weight(returns)
    inv = np.nan_to_num(inv, nan=0.0)
    return inv / inv.sum()


def _mean_variance(
    returns: pd.DataFrame, convictions: dict[str, float] | None = None
) -> np.ndarray:
    """Max-Sharpe mean-variance optimization, long-only, weights sum to 1.

    Uses conviction (if provided) to *blend* mean return estimates:
    expected_return = α * historical_mean + (1-α) * conviction_proxy
    where conviction_proxy scales 0-100 → return target.
    """
    tickers = list(returns.columns)
    n = len(tickers)

    # Estimated mean returns (annualized)
    mu_hist = returns.mean().values * 252

    if convictions:
        # Map conviction [0..100] to expected annual return [-0.10..+0.30]
        c = np.array([float(convictions.get(t, 50.0)) for t in tickers])
        # 0 → -10%, 50 → +10%, 100 → +30%
        mu_conv = -0.10 + 0.40 * (c / 100.0)
        mu = 0.5 * mu_hist + 0.5 * mu_conv
    else:
        mu = mu_hist

    cov = returns.cov().values * 252  # annualized covariance
    # Stabilize: shrink covariance slightly toward identity
    cov = 0.95 * cov + 0.05 * np.eye(n) * np.trace(cov) / n

    # Analytical max-Sharpe (long-only via scipy constrained optimizer)
    from scipy.optimize import minimize

    def neg_sharpe(w: np.ndarray) -> float:
        ret = float(w @ mu)
        vol = float(np.sqrt(w @ cov @ w))
        if vol <= 0:
            return 1e9
        return -(ret / vol)

    bounds = [(0.0, 1.0)] * n
    constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    x0 = np.full(n, 1.0 / n)

    try:
        res = minimize(
            neg_sharpe,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 200, "ftol": 1e-8},
        )
        if res.success:
            w = res.x
            w = np.where(w < 1e-4, 0.0, w)  # zero out noise
            if w.sum() > 0:
                return w / w.sum()
        logger.warning(
            "mean_variance: SLSQP did not converge (%s); falling back to equal weight",
            getattr(res, "message", "no message"),
        )
    except Exception as exc:
        logger.warning("mean_variance: solve failed (%s); falling back to equal weight", exc)

    # The caller asked for a max-Sharpe allocation and is about to receive 1/N.
    # Returning it silently means an optimisation that never happened is
    # indistinguishable from one that did.
    return _equal_weight(returns)


def _hrp(returns: pd.DataFrame, convictions: dict[str, float] | None = None) -> np.ndarray:  # noqa: ARG001
    """Hierarchical Risk Parity (Lopez de Prado 2016).

    Algorithm:
      1. Correlation → distance matrix
      2. Hierarchical clustering (single-linkage)
      3. Quasi-diagonalize to order assets
      4. Recursive bisection with inverse-variance allocation
    """
    cols = list(returns.columns)
    n = len(cols)
    if n < 2:
        return _equal_weight(returns)

    # Canonicalise the basket before clustering.
    #
    # scipy's `linkage` may emit an equivalent dendrogram with a subtree's
    # children in the opposite order when the same assets arrive in a different
    # column order. The bisection below splits the leaf order at its midpoint,
    # so a mirrored subtree splits a different set of names and allocates
    # differently — measured at up to four percentage points of weight on a
    # five-name basket. The weights still summed to one, so nothing downstream
    # could see it: the same portfolio optimised differently depending on the
    # order a caller happened to list it in.
    canonical = sorted(cols, key=str)
    if cols != canonical:
        reordered = _hrp(returns[canonical], convictions)
        return pd.Series(reordered, index=canonical).reindex(cols).to_numpy()

    cov = returns.cov().values
    corr = returns.corr().values
    corr = np.nan_to_num(corr, nan=0.0)

    # A constant return series — a halted name, or a gap filled with zeros — has
    # no variance to allocate against and no correlation to cluster on. The
    # allocation below still sums to 1, so nothing downstream looks wrong; say
    # so here rather than let it pass as a considered weight.
    flat = [cols[i] for i, v in enumerate(np.diag(cov)) if not v > 0]
    if flat:
        logger.warning(
            "HRP: %s have zero return variance; their weights are not risk-derived",
            ", ".join(map(str, flat)),
        )

    # Distance matrix (proper distance metric: d = sqrt(0.5 * (1 - corr)))
    dist = np.sqrt(np.clip(0.5 * (1 - corr), 0, 1))
    np.fill_diagonal(dist, 0.0)
    condensed = squareform(dist, checks=False)

    # Hierarchical cluster
    link = linkage(condensed, method="single")

    # Quasi-diagonalize — extract the leaf order
    order = _leaf_order(link, n)

    # Recursive bisection
    weights = pd.Series(1.0, index=order)
    clusters = [order]
    while clusters:
        new_clusters: list[list[int]] = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            mid = len(cluster) // 2
            left = cluster[:mid]
            right = cluster[mid:]

            var_left = _cluster_var(cov, left)
            var_right = _cluster_var(cov, right)
            alpha = 1 - var_left / (var_left + var_right) if (var_left + var_right) > 0 else 0.5

            for i in left:
                weights.loc[i] *= alpha
            for i in right:
                weights.loc[i] *= 1 - alpha

            new_clusters.append(left)
            new_clusters.append(right)
        clusters = new_clusters

    # Re-order to match original DataFrame column order
    out = np.zeros(n)
    for pos_idx, w in weights.items():
        out[pos_idx] = w
    total = out.sum()
    return out / total if total > 0 else _equal_weight(returns)


def _leaf_order(link: np.ndarray, n: int) -> list[int]:
    """Extract the leaf ordering from a linkage matrix."""
    # Build a recursive leaf-list by walking the linkage tree
    root = 2 * n - 2

    def walk(node: int) -> list[int]:
        if node < n:
            return [int(node)]
        left, right = int(link[node - n, 0]), int(link[node - n, 1])
        return walk(left) + walk(right)

    return walk(root)


def _cluster_var(cov: np.ndarray, cluster: list[int]) -> float:
    """Variance of an inverse-variance-weighted sub-portfolio.

    The floor is load-bearing. A zero-variance leg makes `1 / var` infinite, and
    `inf / inf` is nan; nan then fails the `(var_left + var_right) > 0` test in
    the caller, which falls through to alpha = 0.5. The result is that a single
    constant series silently turns the whole bisection into a naive half-split
    that still sums to 1 and looks like a considered allocation. Flooring
    relative to the cluster's own scale keeps the arithmetic finite, so a
    near-riskless leg dominates its cluster — which is what inverse variance
    means — instead of erasing the risk model.
    """
    sub = cov[np.ix_(cluster, cluster)]
    var = np.diag(sub).astype(float)
    scale = float(np.max(var)) if var.size and float(np.max(var)) > 0 else 1.0
    ivp = 1.0 / np.maximum(var, scale * 1e-12)
    ivp = ivp / ivp.sum()
    return float(ivp @ sub @ ivp)


# ------------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------------


METHOD_REGISTRY = {
    "equal_weight": _equal_weight,
    "conviction_weighted": _conviction_weighted,
    "inverse_vol": _inverse_vol,
    "mean_variance": _mean_variance,
    "hrp": _hrp,
}


METHOD_META: dict[str, MethodMeta] = {
    "equal_weight": MethodMeta(
        id="equal_weight",
        name="Equal Weight",
        description="1/N across the basket. Hard-to-beat baseline — ignores both returns and risk.",
        uses_conviction=False,
        uses_returns=False,
        category="baseline",
    ),
    "conviction_weighted": MethodMeta(
        id="conviction_weighted",
        name="AI Conviction Weighted",
        description=(
            "Weight proportional to AI conviction score. Low-conviction names (<40) "
            "get zero weight — the thesis drives the book."
        ),
        uses_conviction=True,
        uses_returns=False,
        category="signal",
    ),
    "inverse_vol": MethodMeta(
        id="inverse_vol",
        name="Inverse Volatility",
        description=(
            "Weight ∝ 1/σ — simpler cousin of risk parity. "
            "Tames high-vol names without requiring correlations."
        ),
        uses_conviction=False,
        uses_returns=True,
        category="risk",
    ),
    "mean_variance": MethodMeta(
        id="mean_variance",
        name="Mean-Variance (Max Sharpe)",
        description=(
            "Classical Markowitz. If convictions provided, blends 50/50 with historical "
            "means (avoids garbage-in-garbage-out from pure history)."
        ),
        uses_conviction=True,
        uses_returns=True,
        category="optimization",
    ),
    "hrp": MethodMeta(
        id="hrp",
        name="Hierarchical Risk Parity",
        description=(
            "Lopez de Prado 2016. Clusters by correlation, recursive inverse-variance "
            "allocation. Robust to estimation error — no covariance inversion needed."
        ),
        uses_conviction=False,
        uses_returns=True,
        category="risk",
    ),
}


def optimize_weights(
    method: str,
    returns: pd.DataFrame,
    convictions: dict[str, float] | None = None,
) -> np.ndarray:
    if method not in METHOD_REGISTRY:
        raise KeyError(f"Unknown method '{method}'. Available: {sorted(METHOD_REGISTRY)}")
    fn = METHOD_REGISTRY[method]
    w = fn(returns, convictions)
    # Final sanity: clip and normalize
    w = np.clip(w, 0.0, 1.0)
    total = w.sum()
    if total <= 0:
        return np.full(len(returns.columns), 1.0 / len(returns.columns))
    return w / total
