"""Maximum mean discrepancy — scoring a regime labelling that has no answer key.

This is the half of the paper worth having even if the clustering were never
adopted. Real market data has no regime labels, so "did this clustering work?"
normally gets answered by looking at a chart and nodding. The MMD answers it
with a number, and the number is falsifiable.

The quantity is a two-sample test statistic (Gretton et al., via the paper's
Def. 1.7): embed two samples in a reproducing kernel Hilbert space and measure
how far apart their means land. Zero means the two samples are
indistinguishable to the kernel; larger means more distinguishable. From that,
two scores the paper defines and this module computes:

    self-similarity (their Def. 1.9)  low is good
        Draw pairs of windows from *inside* one cluster and measure their MMD.
        If a cluster is a real regime, its members should look like draws from
        one distribution, and the statistic should sit near zero.

    separation                        high is good
        The same statistic across the two clusters. If it is no larger than
        the within-cluster figure, the "regimes" are one population cut in
        half — which is what a threshold on a continuous ratio always
        produces, and is precisely the failure the old volatility-ratio label
        could never have reported about itself.

The ratio of the two is the headline: a labelling scores well when windows
inside a cluster resemble each other more than they resemble the other
cluster's. That test can be run against *any* labelling of the same windows,
so the previous rule and this one can be compared on one scale — see
:func:`score_labelling`.

ONE DELIBERATE DEPARTURE FROM THE PAPER

They fix the Gaussian kernel bandwidth at sigma = 0.1 for hourly SPY. A fixed
bandwidth is not portable across single names: daily log-returns for a utility
and for a biotech differ by an order of magnitude in scale, and one sigma
would saturate the kernel for one and flatten it for the other, making the
scores incomparable between tickers — which is most of what they are for here.
So the default is the median heuristic (sigma = median pairwise distance),
which is the standard scale-free choice. Pass ``sigma`` to reproduce the
paper's setting exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

Float = NDArray[np.float64]
Int = NDArray[np.int64]

#: Pair draws per score. The paper uses 10^5–10^6 on hourly data; the medians
#: here are stable in the low hundreds because a daily corpus holds a few
#: hundred windows in total, and the whole analysis has to answer inside a
#: web request.
DRAWS = 240


def median_sigma(x: Float, y: Float) -> float:
    """The median heuristic: sigma is the median pairwise distance.

    Falls back to the pooled standard deviation when the median distance is
    zero, which happens for a constant stretch — a halted or thinly quoted
    name — where every return is identical and the kernel would divide by nought.
    """
    pooled = np.concatenate([np.ravel(x), np.ravel(y)])
    if pooled.size > 400:  # a subsample is plenty for a bandwidth
        pooled = pooled[:: pooled.size // 400]
    d = np.abs(pooled[:, None] - pooled[None, :])
    med = float(np.median(d[d > 0])) if np.any(d > 0) else 0.0
    if med > 0:
        return med
    sd = float(pooled.std())
    return sd if sd > 0 else 1.0


def mmd2(x: Float, y: Float, sigma: float) -> float:
    """Biased empirical MMD^2 under a Gaussian kernel (their eq. 53).

    Biased — the V-statistic, with the diagonal left in — because that is the
    estimator the paper uses and it is non-negative, which matters when the
    number is shown to a reader. The unbiased form can come out negative for
    two identical samples and "a separation of -0.0003" is not a sentence
    anyone should have to interpret.
    """
    x = np.ravel(np.asarray(x, dtype=np.float64))
    y = np.ravel(np.asarray(y, dtype=np.float64))
    if x.size == 0 or y.size == 0:
        return float("nan")
    denom = 2.0 * sigma * sigma
    if denom <= 0:
        return float("nan")

    def k(a: Float, b: Float) -> float:
        d = a[:, None] - b[None, :]
        return float(np.exp(-(d * d) / denom).mean())

    return max(0.0, k(x, x) + k(y, y) - 2.0 * k(x, y))


def _pairs(n: int, draws: int, rng: np.random.Generator) -> list[tuple[int, int]]:
    """Distinct index pairs, sampled without replacement where possible."""
    if n < 2:
        return []
    total = n * (n - 1) // 2
    if total <= draws:
        return [(i, j) for i in range(n) for j in range(i + 1, n)]
    seen: set[tuple[int, int]] = set()
    while len(seen) < draws:
        i, j = rng.integers(n), rng.integers(n)
        if i == j:
            continue
        seen.add((int(min(i, j)), int(max(i, j))))
    return sorted(seen)


def self_similarity(
    members: Float,
    *,
    sigma: float | None = None,
    draws: int = DRAWS,
    seed: int = 0,
) -> float:
    """Median MMD^2 between pairs of windows drawn from one cluster.

    Their Def. 1.9. Median rather than mean, as in the paper: one crash window
    inside an otherwise homogeneous cluster should not be able to set the
    score for the whole cluster.
    """
    members = np.asarray(members, dtype=np.float64)
    if members.ndim != 2 or members.shape[0] < 2:
        return float("nan")
    rng = np.random.default_rng(seed)
    s = median_sigma(members, members) if sigma is None else sigma
    vals = [mmd2(members[i], members[j], s) for i, j in _pairs(members.shape[0], draws, rng)]
    return float(np.median(vals)) if vals else float("nan")


def separation(
    a: Float,
    b: Float,
    *,
    sigma: float | None = None,
    draws: int = DRAWS,
    seed: int = 0,
) -> float:
    """Median MMD^2 between windows drawn one from each cluster."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.ndim != 2 or b.ndim != 2 or a.shape[0] == 0 or b.shape[0] == 0:
        return float("nan")
    rng = np.random.default_rng(seed)
    s = median_sigma(a, b) if sigma is None else sigma
    n = min(draws, a.shape[0] * b.shape[0])
    ia = rng.integers(a.shape[0], size=n)
    ib = rng.integers(b.shape[0], size=n)
    vals = [mmd2(a[i], b[j], s) for i, j in zip(ia, ib, strict=True)]
    return float(np.median(vals)) if vals else float("nan")


@dataclass(frozen=True)
class Verdict:
    """How well one labelling of one set of windows holds up.

    ``ratio`` is the number to read: separation divided by the worst
    within-cluster score. Above 1 the clusters are further apart than their
    own members are from each other. At or below 1 the labelling has cut one
    population in half, whatever the chart looks like.
    """

    within: list[float]
    between: float
    ratio: float
    sigma: float
    draws: int
    clusters: list[int] = field(default_factory=list)

    @property
    def holds(self) -> bool:
        return bool(np.isfinite(self.ratio) and self.ratio > 1.0)

    def as_dict(self) -> dict[str, object]:
        return {
            "within": [_clean(v) for v in self.within],
            "between": _clean(self.between),
            "ratio": _clean(self.ratio),
            "holds": self.holds,
            "sigma": _clean(self.sigma),
            "draws": self.draws,
            "cluster_sizes": self.clusters,
        }


def _clean(v: float) -> float | None:
    return None if v is None or not np.isfinite(v) else round(float(v), 6)


def score_labelling(
    wins: Float,
    labels: Int,
    *,
    sigma: float | None = None,
    draws: int = DRAWS,
    seed: int = 0,
) -> Verdict:
    """Score *any* labelling of the same windows — ours, or the old rule's.

    Taking the labels as an argument rather than doing the clustering is what
    makes the comparison fair: the volatility-ratio rule and WK-means get
    scored on identical windows with an identical kernel and an identical
    number of draws, so the only thing that differs between the two numbers is
    the labelling itself.
    """
    wins = np.asarray(wins, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64)
    if wins.shape[0] != labels.size:
        raise ValueError(f"{wins.shape[0]} windows but {labels.size} labels")

    present = [int(v) for v in np.unique(labels) if np.sum(labels == v) >= 2]
    s = median_sigma(wins, wins) if sigma is None else sigma

    within = [
        self_similarity(wins[labels == c], sigma=s, draws=draws, seed=seed + c) for c in present
    ]
    if len(present) >= 2:
        between = separation(
            wins[labels == present[0]],
            wins[labels == present[-1]],
            sigma=s,
            draws=draws,
            seed=seed,
        )
    else:
        between = float("nan")

    worst = max((v for v in within if np.isfinite(v)), default=float("nan"))
    ratio = (
        between / worst
        if np.isfinite(between) and np.isfinite(worst) and worst > 0
        else float("nan")
    )

    return Verdict(
        within=within,
        between=between,
        ratio=ratio,
        sigma=s,
        draws=draws,
        clusters=[int(np.sum(labels == c)) for c in present],
    )
