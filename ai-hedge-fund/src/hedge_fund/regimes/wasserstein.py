"""Wasserstein k-means — clustering return windows by their whole distribution.

Horvath, Issa and Muguruza, *Clustering Market Regimes Using the Wasserstein
Distance* (SSRN 3947905). The idea is a change of subject rather than a change
of algorithm: instead of reducing each window of returns to a few numbers and
clustering those numbers, cluster the *distributions* themselves.

Why that matters here. The regime metric this replaces compared one window's
realised volatility against a longer baseline and cut the ratio at 1.25 and
0.8. That is the second moment and two thresholds nobody derived. The paper
benchmarks exactly that family — its "MK-means" uses the first *p* moments,
properly standardised, so it is strictly more informed than a vol ratio — and
on jump-driven returns it recovers 27% of regime changes against this method's
87% (their Table 4). Equity returns jump. A vol ratio is fine right up until
the week it is being asked about.

WHAT MAKES IT CHEAP

In one dimension the optimal transport problem has a closed form and no
solver is needed (their eq. 17, 21). For two windows of equal length, sort
both and average the absolute differences of the sorted values:

    W1(mu, nu) = (1/N) * sum_i |alpha_i - beta_i|

and the barycentre — the "average" of a family of distributions, which is what
a centroid has to be on this space — is the pointwise median of the sorted
vectors (their Prop. 2.6). Sort once up front and both operations are plain
numpy over an (M, N) array. No optimal-transport dependency, no sklearn.

WHAT IT IS NOT

The clustering is fitted over the whole path at once, so a window's label was
assigned with the rest of history — including its future — in view. The paper
is explicit that this is an *a posteriori* method and so is this module:
:func:`wk_means` is safe for describing where a company has been, and is not
safe to trade on. Anything walking forward through time must refit on data
available at each step. See ``docs/regimes.md``.

It also labels rather than predicts. Which regime you are in now says nothing
here about which comes next; the paper never claims otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Float = NDArray[np.float64]
Int = NDArray[np.int64]

#: Below this many windows a k-means fit is fitting noise. The paper's own
#: window-length sweep (their Fig. 15) collapses once the windows stop
#: containing a regime change; this is the cruder version of the same guard.
MIN_WINDOWS = 12


class RegimeError(ValueError):
    """Not enough data, or a parameter that cannot produce a clustering."""


# ── the lift: a price path becomes a family of distributions ───────────────


def log_returns(closes: Float) -> Float:
    """Log-returns of a close series (their eq. 2), non-finite steps dropped.

    Zero and negative closes appear in real provider data — a bad split
    adjustment, a placeholder row — and ``log`` turns them into ``-inf``
    rather than an error, which would then poison every window containing
    them and quietly move a centroid.
    """
    closes = np.asarray(closes, dtype=np.float64)
    if closes.size < 2:
        return np.empty(0, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = np.diff(np.log(closes))
    return rets[np.isfinite(rets)]


def windows(rets: Float, h1: int, h2: int) -> Float:
    """Overlapping windows of length ``h1``, stepping ``h1 - h2`` (their eq. 3).

    ``h2`` is the overlap, so ``h2 = 0`` gives disjoint windows and a large
    ``h2`` gives a dense, slow-moving family. The paper's (35, 28) means a
    35-bar window advancing 7 bars at a time.

    Returns an ``(M, h1)`` array, one row per window, in time order.
    """
    if h1 < 2:
        raise RegimeError("a window needs at least 2 returns")
    if not 0 <= h2 < h1:
        raise RegimeError(f"overlap must be in [0, {h1}), got {h2}")
    step = h1 - h2
    rets = np.asarray(rets, dtype=np.float64)
    count = 1 + (rets.size - h1) // step if rets.size >= h1 else 0
    if count <= 0:
        raise RegimeError(
            f"{rets.size} returns cannot fill a {h1}-return window; "
            "ask for more history or a shorter window"
        )
    idx = np.arange(h1)[None, :] + (np.arange(count) * step)[:, None]
    return np.asarray(rets[idx], dtype=np.float64)


def window_spans(count: int, h1: int, h2: int) -> list[tuple[int, int]]:
    """``[start, end)`` index of each window *into the returns array*.

    Kept separate from :func:`windows` so a caller can map a label back onto
    dates without carrying the window contents around.
    """
    step = h1 - h2
    return [(i * step, i * step + h1) for i in range(count)]


# ── the metric and the aggregator ──────────────────────────────────────────


def w1(a_sorted: Float, b_sorted: Float) -> float:
    """1-Wasserstein distance between two equal-size empirical measures.

    Both arguments must already be sorted ascending — that is the whole
    optimisation (their eq. 21). Passing unsorted input returns a number that
    is not a distance rather than raising, so sorting is done once by the
    caller and never per comparison.
    """
    return float(np.abs(a_sorted - b_sorted).mean())


def _w1_to_centroids(sorted_wins: Float, centroids: Float) -> Float:
    """``(M, k)`` distance from every window to every centroid."""
    gap = np.abs(sorted_wins[:, None, :] - centroids[None, :, :]).mean(axis=2)
    return np.asarray(gap, dtype=np.float64)


def barycentre(sorted_wins: Float) -> Float:
    """The 1-Wasserstein barycentre of a family of measures (their Prop. 2.6).

    The pointwise median of the sorted windows — the j-th atom of the result
    is the median of every window's j-th smallest return. Median rather than
    mean is the entire robustness story: one crash window moves a mean
    centroid and cannot move a median one, which is why the moment-based
    benchmark ends up clustering outliers instead of regimes.
    """
    return np.median(sorted_wins, axis=0)


# ── the algorithm ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Clustering:
    """The outcome of one WK-means fit.

    ``labels`` index into ``centroids``, which are ordered calm-first: label 0
    is always the least dispersed regime. See :func:`_order_by_dispersion`.
    """

    labels: Int
    centroids: Float
    dispersion: Float  # centroid spread, in the units of the returns
    inertia: float  # mean W1 from each window to its own centroid
    iterations: int
    converged: bool

    @property
    def k(self) -> int:
        return int(self.centroids.shape[0])


def _kmeans_plus_plus(sorted_wins: Float, k: int, rng: np.random.Generator) -> Float:
    """Seeding, in W1 rather than Euclidean distance.

    The paper samples k windows uniformly. That is fine on their hourly SPY
    corpus and is not fine here: on daily data a calm stretch outnumbers a
    turbulent one heavily enough that a uniform draw regularly takes both
    seeds from the same regime, and the fit then splits calm in half and calls
    the quiet half a regime. k-means++ picks each later seed with probability
    proportional to its squared distance from the nearest existing one, which
    is the standard fix and changes nothing about the objective.
    """
    m = sorted_wins.shape[0]
    first = int(rng.integers(m))
    picked = [first]
    d2 = np.abs(sorted_wins - sorted_wins[first]).mean(axis=1) ** 2
    for _ in range(1, k):
        total = float(d2.sum())
        if total <= 0:  # every window identical — any pick is as good
            nxt = int(rng.integers(m))
        else:
            nxt = int(rng.choice(m, p=d2 / total))
        picked.append(nxt)
        d2 = np.minimum(d2, np.abs(sorted_wins - sorted_wins[nxt]).mean(axis=1) ** 2)
    return sorted_wins[picked].copy()


def _order_by_dispersion(centroids: Float, labels: Int) -> tuple[Float, Int, Float]:
    """Relabel so cluster 0 is the calmest, k-1 the most turbulent.

    k-means numbers its clusters by whatever the seeding happened to do, so
    "cluster 1" means nothing across two runs, two tickers, or two window
    lengths. Everything downstream — a colour, a stored label, an eval —
    would be comparing arbitrary integers.

    Dispersion is the centroid's own standard deviation: the barycentre *is* a
    distribution, so its spread is the natural ordering and it is what the
    words calm and turbulent are pointing at.
    """
    spread = centroids.std(axis=1)
    order = np.argsort(spread, kind="stable")
    remap = np.empty(order.size, dtype=np.int64)
    remap[order] = np.arange(order.size)
    return centroids[order], remap[labels], spread[order]


def wk_means(
    wins: Float,
    k: int = 2,
    *,
    seed: int = 0,
    max_iter: int = 100,
    tol: float = 1e-10,
    restarts: int = 8,
) -> Clustering:
    """Cluster return windows by their distributions (their Algorithm 1).

    ``wins`` is ``(M, N)`` — M windows of N returns, unsorted. Every window
    must be the same length, which is what makes the closed forms apply.

    Deterministic given ``seed``: the same input returns the same labels, which
    the run record depends on. ``restarts`` runs the fit several times from
    different seeds and keeps the lowest-inertia result, because k-means finds
    a local minimum and a single unlucky start is otherwise indistinguishable
    from a finding.
    """
    wins = np.asarray(wins, dtype=np.float64)
    if wins.ndim != 2:
        raise RegimeError(f"expected an (M, N) array of windows, got shape {wins.shape}")
    m, n = wins.shape
    if m < MIN_WINDOWS:
        raise RegimeError(
            f"{m} windows is too few to cluster (need {MIN_WINDOWS}); "
            "ask for more history, or a shorter window with more overlap"
        )
    if not 2 <= k <= m:
        raise RegimeError(f"k must be between 2 and {m}, got {k}")

    sorted_wins = np.sort(wins, axis=1)

    best: Clustering | None = None
    for r in range(max(1, restarts)):
        got = _fit_once(sorted_wins, k, np.random.default_rng(seed + r), max_iter, tol)
        if got is None:
            continue
        if best is None or got.inertia < best.inertia:
            best = got
    if best is None:
        raise RegimeError(
            "every fit collapsed to fewer than k non-empty clusters — "
            "the windows are too alike to separate at this k"
        )
    return best


def _fit_once(
    sorted_wins: Float,
    k: int,
    rng: np.random.Generator,
    max_iter: int,
    tol: float,
) -> Clustering | None:
    """One Lloyd loop. ``None`` if a cluster emptied and could not be refilled."""
    centroids = _kmeans_plus_plus(sorted_wins, k, rng)
    labels = np.zeros(sorted_wins.shape[0], dtype=np.int64)
    converged = False
    used = 0

    for it in range(1, max_iter + 1):
        used = it
        dists = _w1_to_centroids(sorted_wins, centroids)
        labels = np.asarray(dists.argmin(axis=1), dtype=np.int64)

        nxt = np.empty_like(centroids)
        for j in range(k):
            members = sorted_wins[labels == j]
            if members.size == 0:
                # Re-seed an emptied cluster on the worst-served window rather
                # than dropping to k-1 silently: a fit that quietly returns one
                # cluster reads downstream as "no regimes here", which is a
                # different and much stronger claim than "this fit failed".
                worst = int(dists.min(axis=1).argmax())
                nxt[j] = sorted_wins[worst]
                continue
            nxt[j] = barycentre(members)

        shift = float(np.abs(nxt - centroids).mean(axis=1).sum())  # their eq. 23
        centroids = nxt
        if shift < tol:
            converged = True
            break

    dists = _w1_to_centroids(sorted_wins, centroids)
    labels = np.asarray(dists.argmin(axis=1), dtype=np.int64)
    if np.unique(labels).size < k:
        return None

    inertia = float(dists.min(axis=1).mean())
    centroids, labels, spread = _order_by_dispersion(centroids, labels)
    return Clustering(
        labels=labels,
        centroids=centroids,
        dispersion=spread,
        inertia=inertia,
        iterations=used,
        converged=converged,
    )


def assign(sorted_window: Float, centroids: Float) -> int:
    """Nearest centroid for one already-sorted window, in W1."""
    return int(np.abs(centroids - sorted_window).mean(axis=1).argmin())
