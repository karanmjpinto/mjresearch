"""One price series in, a scored regime labelling out.

This is the layer the API route and the plan metric both call. It does five
things, in this order, and the order is the argument:

    1. Lift the price path into a family of return distributions.
    2. Cluster them in Wasserstein distance (:mod:`.wasserstein`).
    3. Label the *same* windows with the volatility-ratio rule the app used
       before, replayed window by window (:func:`ratio_labels`).
    4. Fit a hidden Markov model to the returns (:mod:`.hmm`) — not for a
       third opinion on the labels, but for the transition matrix, which is
       the only object here that says anything about *order*: how long a
       regime runs, and what follows it.
    5. Score all three labellings with the same kernel and the same number of
       draws (:mod:`.mmd`), and report all three scores.

Step 3 is the part that is easy to leave out and shouldn't be. A new method
that arrives with only its own score attached is asking to be believed; one
that arrives next to the thing it replaces, measured the same way, can be
checked. If the old rule ever scores better on a name, this module says so and
the number is right there in the response. Step 4 is held to the same standard
and generally loses on those scores — see :mod:`.hmm` for why that is expected
and why it is kept anyway.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from hedge_fund.regimes import hmm, mmd, wasserstein as wk
from hedge_fund.regimes.wasserstein import RegimeError

Float = NDArray[np.float64]
Int = NDArray[np.int64]

TRADING_DAYS = 252

#: Defaults for daily bars. The paper's (35, 28) is hourly — 35 bars is about
#: a trading week there and about seven weeks here. 63 trading days is a
#: quarter, which is the shortest window that still holds enough returns for
#: a sample quantile to mean anything, and the 42-day overlap advances it
#: three weeks at a time.
DEFAULT_H1 = 63
DEFAULT_H2 = 42

#: The thresholds the previous `volatility_regime` metric used, kept here so
#: the comparison replays the real rule rather than a flattering version of it.
RATIO_ELEVATED = 1.25
RATIO_SUBDUED = 0.80

#: Ordered names for k clusters, calm first — matching the centroid ordering
#: that `wasserstein._order_by_dispersion` guarantees.
NAMES: dict[int, tuple[str, ...]] = {
    2: ("calm", "turbulent"),
    3: ("calm", "unsettled", "turbulent"),
    4: ("calm", "steady", "unsettled", "turbulent"),
}


def names_for(k: int) -> tuple[str, ...]:
    return NAMES.get(k) or tuple(f"regime {i + 1}" for i in range(k))


# ── the benchmark being replaced ───────────────────────────────────────────


def ratio_labels(wins: Float, rets: Float) -> Int:
    """The old rule, applied window by window: 1 where vol ran hot.

    `volatility_regime` compared one recent window's annualised volatility
    against the whole baseline and cut at 1.25. Replaying it per window gives
    a labelling of exactly the same objects the clustering produces, which is
    the only way the two can be scored against each other.

    Three labels collapse to two here (elevated against everything else)
    because the comparison is about whether stress was identified, and
    "subdued" and "normal" are both claims that it was not.
    """
    baseline = float(np.std(rets))
    if baseline <= 0:
        return np.zeros(wins.shape[0], dtype=np.int64)
    ratio = wins.std(axis=1) / baseline
    return np.asarray(ratio >= RATIO_ELEVATED, dtype=np.int64)


# ── per-return labels from per-window labels ───────────────────────────────


def stress_share(
    labels: Int,
    spans: list[tuple[int, int]],
    n_rets: int,
    stressed_from: int,
) -> Float:
    """For each return, the share of its covering windows that called it stressed.

    Windows overlap, so a single return sits inside several of them and can be
    claimed by more than one cluster — the paper handles this by colouring the
    price path by average membership, and this is that average. Keeping it
    continuous rather than voting immediately is what lets the chart show a
    regime *edge* as a gradient instead of a hard line it cannot justify.

    Returns covered by no window (the tail too short to fill one) come back as
    NaN rather than 0, so "not measured" never renders as "calm".
    """
    total = np.zeros(n_rets)
    hits = np.zeros(n_rets)
    for lbl, (lo, hi) in zip(labels, spans, strict=True):
        hi = min(hi, n_rets)
        hits[lo:hi] += 1
        if lbl >= stressed_from:
            total[lo:hi] += 1
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(hits > 0, total / hits, np.nan)
    return out


# ── result types ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WindowRow:
    """One window: where it sits, what it looks like, and what it was called."""

    start: str
    end: str
    label: int
    #: The window's average *day*, in percent. Deliberately not annualised:
    #: scaling a 63-day mean by 252 turns an ordinary bad quarter into
    #: "-117% a year", which is arithmetically true and tells the reader
    #: nothing about a year. The centroid rows below do annualise, because a
    #: barycentre is a typical-day distribution and a year of typical days is
    #: a statement someone can actually check.
    mean_day_pct: float
    vol_pct: float
    skew: float
    kurtosis: float
    distance: float  # W1 to its own centroid

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "label": self.label,
            "mean_day_pct": _r(self.mean_day_pct, 4),
            "vol_pct": _r(self.vol_pct, 2),
            "skew": _r(self.skew, 3),
            "kurtosis": _r(self.kurtosis, 3),
            "distance": _r(self.distance, 6),
        }


@dataclass(frozen=True)
class CentroidRow:
    """A barycentre, summarised and sampled for drawing."""

    label: int
    name: str
    windows: int
    share_pct: float
    #: Annualised, which is meaningful here: a barycentre is a typical-day
    #: distribution, so a year of typical days is a statement someone can check.
    mean_pct: float
    #: The same centre as a single day. Carried explicitly so a chart plotting
    #: windows (which report days) against centroids never has to divide by 252
    #: itself — getting that wrong puts the centroid marks off the axis, which
    #: is exactly what happened.
    mean_day_pct: float
    vol_pct: float
    skew: float
    kurtosis: float
    worst_day_pct: float
    best_day_pct: float
    #: The centroid's own quantiles, 0 to 1 — it is a distribution, so this is
    #: the honest way to draw it. 41 points is enough for a smooth curve.
    quantiles: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "name": self.name,
            "windows": self.windows,
            "share_pct": _r(self.share_pct, 1),
            "mean_pct": _r(self.mean_pct, 3),
            "mean_day_pct": _r(self.mean_day_pct, 4),
            "vol_pct": _r(self.vol_pct, 2),
            "skew": _r(self.skew, 3),
            "kurtosis": _r(self.kurtosis, 3),
            "worst_day_pct": _r(self.worst_day_pct, 2),
            "best_day_pct": _r(self.best_day_pct, 2),
            "quantiles": [_r(q, 6) for q in self.quantiles],
        }


@dataclass(frozen=True)
class Episode:
    """A maximal stretch of dates the labelling calls one regime."""

    label: int
    name: str
    start: str
    end: str
    days: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "name": self.name,
            "start": self.start,
            "end": self.end,
            "days": self.days,
        }


@dataclass(frozen=True)
class HmmState:
    """One hidden state of the fitted chain, as a reader would describe it."""

    label: int
    name: str
    days: int
    share_pct: float
    #: Mean *daily* log-return, in percent. Deliberately not annualised the way
    #: a centroid's is: a state whose expected run is two days has no annual
    #: drift, and multiplying its mean by 252 prints a number like -400% that
    #: is arithmetic rather than information.
    mean_day_pct: float
    #: Annualised, so it can be read against the centroid rows.
    vol_pct: float
    #: a_jj — the chance tomorrow is this state again, given today is.
    persistence: float
    #: 1 / (1 - a_jj): the run length the fitted chain implies, in trading days.
    expected_days: float
    #: This state's share of tomorrow, from the last day's posterior pushed
    #: one step through A. A description of the fitted history, not a forecast.
    next_day_pct: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "name": self.name,
            "days": self.days,
            "share_pct": _r(self.share_pct, 1),
            "mean_day_pct": _r(self.mean_day_pct, 4),
            "vol_pct": _r(self.vol_pct, 2),
            "persistence": _r(self.persistence, 4),
            "expected_days": _r(self.expected_days, 1),
            "next_day_pct": _r(self.next_day_pct, 1),
        }


@dataclass(frozen=True)
class HmmView:
    """The hidden-Markov half of the answer: states, and how they move.

    Everything here that the clustering cannot also produce comes from
    ``transition``. The rest — states, episodes, a per-day posterior — is
    reported so the two methods can be read against each other rather than
    taken on trust.
    """

    states: list[HmmState]
    #: Row i is the distribution over tomorrow given today is state i.
    transition: list[list[float]]
    current: HmmState
    current_run_days: int
    #: How sure the model is that today is the state Viterbi assigned. The two
    #: can disagree at the very end of a series, where the backward pass has no
    #: future to condition on — see :attr:`.hmm.Fit.next_day`. A low number
    #: here is the reason to distrust ``next_day_pct``.
    current_posterior_pct: float
    episodes: list[Episode]
    #: Per return, P(state is above calm | the whole series). The model's own
    #: uncertainty, where `stress_share` could only report window bookkeeping.
    posterior: list[float]
    loglik: float
    bic: float
    iterations: int
    converged: bool
    verdict: mmd.Verdict

    def as_dict(self) -> dict[str, Any]:
        return {
            "states": [s.as_dict() for s in self.states],
            "transition": [[_r(v, 4) for v in row] for row in self.transition],
            "current": {
                **self.current.as_dict(),
                "run_days": self.current_run_days,
                "posterior_pct": _r(self.current_posterior_pct, 1),
            },
            "episodes": [e.as_dict() for e in self.episodes],
            "posterior": [_r(v, 3) for v in self.posterior],
            "fit": {
                "loglik": _r(self.loglik, 2),
                "bic": _r(self.bic, 1),
                "iterations": self.iterations,
                "converged": self.converged,
            },
        }


@dataclass(frozen=True)
class Analysis:
    ticker: str
    k: int
    h1: int
    h2: int
    seed: int
    observations: int
    first_date: str
    last_date: str
    windows: list[WindowRow]
    centroids: list[CentroidRow]
    episodes: list[Episode]
    dates: list[str]
    closes: list[float]
    stress: list[float | None]
    current: CentroidRow
    current_run_days: int
    inertia: float
    iterations: int
    converged: bool
    verdict: mmd.Verdict
    baseline_verdict: mmd.Verdict
    #: None when the chain would not fit — a short or degenerate series. The
    #: clustering half of the response stands on its own, so a failed fit
    #: drops this key rather than failing the request.
    hmm: HmmView | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "params": {
                "k": self.k,
                "window_days": self.h1,
                "overlap_days": self.h2,
                "seed": self.seed,
            },
            "coverage": {
                "observations": self.observations,
                "first_date": self.first_date,
                "last_date": self.last_date,
                "windows": len(self.windows),
            },
            "fit": {
                "inertia": _r(self.inertia, 6),
                "iterations": self.iterations,
                "converged": self.converged,
            },
            "current": {
                **self.current.as_dict(),
                "run_days": self.current_run_days,
            },
            "centroids": [c.as_dict() for c in self.centroids],
            "windows_detail": [w.as_dict() for w in self.windows],
            "episodes": [e.as_dict() for e in self.episodes],
            "path": {
                "dates": self.dates,
                "closes": [_r(c, 4) for c in self.closes],
                "stress": [None if s is None else _r(s, 3) for s in self.stress],
            },
            "hmm": None if self.hmm is None else self.hmm.as_dict(),
            "validation": {
                "wasserstein": self.verdict.as_dict(),
                "volatility_ratio": self.baseline_verdict.as_dict(),
                "hmm": None if self.hmm is None else self.hmm.verdict.as_dict(),
                "note": (
                    "All labellings scored on the same windows with the same "
                    "kernel and the same number of draws. Ratio above 1 means "
                    "windows resemble their own cluster more than the other. "
                    "The HMM is expected to score below the clustering here — "
                    "it earns its place with the transition matrix, not the "
                    "labels."
                ),
            },
            "caveats": CAVEATS,
        }


#: Said in the payload, not only in the docs, because the response is what
#: gets read. Every one of these is a limitation the paper states about itself.
CAVEATS = [
    "Fitted over the whole window at once, so a label used the rest of the "
    "history — including what came after it. Descriptive only: not a signal, "
    "and not safe to backtest on.",
    "The clustering names the regime you are in, never the one coming next. "
    "Only the hidden chain's transition matrix speaks to what follows, and it "
    "speaks about this history rather than about tomorrow.",
    "k is chosen, not discovered. Two is a convention, not a finding.",
    "One company at a time. There is no portfolio-level regime here.",
    "The transition matrix describes how this history switched. It was fitted "
    "using the whole series, the end included, so tomorrow's probabilities are "
    "a summary of the past, not a forecast you could have acted on.",
    "The hidden states are Gaussian. Equity returns jump, so a large move is "
    "more likely to widen a state than to switch one.",
]


def _r(v: float | None, places: int) -> float | None:
    if v is None:
        return None
    f = float(v)
    return None if not math.isfinite(f) else round(f, places)


def _moment(x: Float, order: int) -> float:
    """Standardised central moment — skew at 3, kurtosis at 4 (excess)."""
    sd = float(x.std())
    if sd <= 0 or x.size < 4:
        return float("nan")
    m = float((((x - x.mean()) / sd) ** order).mean())
    return m - 3.0 if order == 4 else m


# ── the entry point ────────────────────────────────────────────────────────


def analyse(
    closes: Float,
    dates: list[str],
    *,
    ticker: str = "",
    k: int = 2,
    h1: int = DEFAULT_H1,
    h2: int = DEFAULT_H2,
    seed: int = 0,
    draws: int = mmd.DRAWS,
    with_hmm: bool = True,
) -> Analysis:
    """Cluster a close series into regimes and score the result.

    ``dates`` must be the same length as ``closes``; returns are dated by the
    close that ends them, so return ``i`` carries ``dates[i + 1]``.

    ``with_hmm`` is on by default and costs a few tenths of a second. Turn it
    off where only the labelling is wanted — the plan metric does, because it
    reports a regime name and never reads a transition.
    """
    closes = np.asarray(closes, dtype=np.float64)
    if closes.size != len(dates):
        raise RegimeError(f"{closes.size} closes but {len(dates)} dates")
    rets = wk.log_returns(closes)
    if rets.size + 1 != closes.size:
        # Non-finite steps were dropped; realign so dates keep meaning something.
        keep = np.isfinite(np.concatenate([[0.0], np.diff(np.log(np.abs(closes) + 1e-300))]))
        closes = closes[keep]
        dates = [d for d, on in zip(dates, keep, strict=True) if on]
        rets = wk.log_returns(closes)
    if rets.size < h1 + 2:
        raise RegimeError(
            f"{rets.size} usable returns cannot fill a {h1}-day window; "
            "ask for more history or a shorter window"
        )

    wins = wk.windows(rets, h1, h2)
    spans = wk.window_spans(wins.shape[0], h1, h2)
    fit = wk.wk_means(wins, k=k, seed=seed)
    names = names_for(fit.k)

    sorted_wins = np.sort(wins, axis=1)
    dist = np.abs(sorted_wins[:, None, :] - fit.centroids[None, :, :]).mean(axis=2)
    own = dist[np.arange(wins.shape[0]), fit.labels]

    ann = math.sqrt(TRADING_DAYS) * 100
    rows = [
        WindowRow(
            start=dates[lo + 1],
            end=dates[min(hi, len(dates) - 1)],
            label=int(fit.labels[i]),
            mean_day_pct=float(wins[i].mean()) * 100,
            vol_pct=float(wins[i].std()) * ann,
            skew=_moment(wins[i], 3),
            kurtosis=_moment(wins[i], 4),
            distance=float(own[i]),
        )
        for i, (lo, hi) in enumerate(spans)
    ]

    qs = np.linspace(0.0, 1.0, 41)
    centroids: list[CentroidRow] = []
    for j in range(fit.k):
        member = wins[fit.labels == j]
        c = fit.centroids[j]
        centroids.append(
            CentroidRow(
                label=j,
                name=names[j],
                windows=int(member.shape[0]),
                share_pct=100.0 * member.shape[0] / wins.shape[0],
                mean_pct=float(c.mean()) * TRADING_DAYS * 100,
                mean_day_pct=float(c.mean()) * 100,
                vol_pct=float(c.std()) * ann,
                skew=_moment(c, 3),
                kurtosis=_moment(c, 4),
                worst_day_pct=float(c.min()) * 100,
                best_day_pct=float(c.max()) * 100,
                quantiles=[float(v) for v in np.quantile(c, qs)],
            )
        )

    # Per-return membership, then the episodes a reader actually names.
    share = stress_share(fit.labels, spans, rets.size, stressed_from=1)
    per_ret = _per_return_label(fit.labels, spans, rets.size, fit.k)
    episodes = _episodes(per_ret, dates, names)
    current = centroids[int(fit.labels[-1])]
    run = episodes[-1].days if episodes else 0

    verdict = mmd.score_labelling(wins, fit.labels, draws=draws, seed=seed)
    base = mmd.score_labelling(
        wins, ratio_labels(wins, rets), sigma=verdict.sigma, draws=draws, seed=seed
    )
    chain = (
        _hmm_view(rets, dates, wins, spans, k=k, seed=seed, sigma=verdict.sigma, draws=draws)
        if with_hmm
        else None
    )

    return Analysis(
        ticker=ticker,
        k=fit.k,
        h1=h1,
        h2=h2,
        seed=seed,
        observations=int(closes.size),
        first_date=dates[0],
        last_date=dates[-1],
        windows=rows,
        centroids=centroids,
        episodes=episodes,
        dates=dates[1:],
        closes=[float(v) for v in closes[1:]],
        stress=[None if not math.isfinite(s) else float(s) for s in share],
        current=current,
        current_run_days=run,
        inertia=fit.inertia,
        iterations=fit.iterations,
        converged=fit.converged,
        verdict=verdict,
        baseline_verdict=base,
        hmm=chain,
    )


def _hmm_view(
    rets: Float,
    dates: list[str],
    wins: Float,
    spans: list[tuple[int, int]],
    *,
    k: int,
    seed: int,
    sigma: float,
    draws: int,
) -> HmmView | None:
    """Fit the chain and describe it, or return None if it will not fit.

    The window labels handed to :mod:`.mmd` are the majority Viterbi state
    inside each window, so the HMM is scored on exactly the objects the
    clustering was scored on, with the bandwidth the clustering's own verdict
    chose. Anything else and the two numbers would not be comparable, which is
    the only reason to compute them.
    """
    try:
        fitted = hmm.fit(rets, k=k, seed=seed)
    except RegimeError:
        return None

    names = names_for(fitted.k)
    ann = math.sqrt(TRADING_DAYS) * 100
    nxt = fitted.next_day
    states = [
        HmmState(
            label=j,
            name=names[j],
            days=int(np.sum(fitted.path == j)),
            share_pct=100.0 * float(np.mean(fitted.path == j)),
            mean_day_pct=float(fitted.means[j]) * 100,
            vol_pct=float(fitted.sigmas[j]) * ann,
            persistence=float(fitted.persistence[j]),
            expected_days=float(fitted.expected_days[j]),
            next_day_pct=100.0 * float(nxt[j]),
        )
        for j in range(fitted.k)
    ]

    episodes = _episodes(fitted.path, dates, names)
    today = int(fitted.path[-1])
    window_labels = np.array(
        [
            int(np.bincount(fitted.path[lo : min(hi, rets.size)], minlength=fitted.k).argmax())
            for lo, hi in spans
        ],
        dtype=np.int64,
    )
    verdict = mmd.score_labelling(wins, window_labels, sigma=sigma, draws=draws, seed=seed)

    return HmmView(
        states=states,
        transition=[[float(v) for v in row] for row in fitted.transition],
        current=states[today],
        current_run_days=episodes[-1].days if episodes else 0,
        current_posterior_pct=100.0 * float(fitted.gamma[-1, today]),
        episodes=episodes,
        posterior=[float(v) for v in fitted.gamma[:, 1:].sum(axis=1)],
        loglik=fitted.loglik,
        bic=fitted.bic,
        iterations=fitted.iterations,
        converged=fitted.converged,
        verdict=verdict,
    )


def _per_return_label(labels: Int, spans: list[tuple[int, int]], n: int, k: int) -> Int:
    """Majority label among the windows covering each return; -1 if none do."""
    votes = np.zeros((n, k))
    for lbl, (lo, hi) in zip(labels, spans, strict=True):
        votes[lo : min(hi, n), int(lbl)] += 1
    covered = votes.sum(axis=1) > 0
    out = np.full(n, -1, dtype=np.int64)
    # Ties go to the more turbulent cluster: on an edge, over-calling stress
    # is the cheaper error of the two, and argmax on reversed columns does it.
    out[covered] = k - 1 - votes[covered, ::-1].argmax(axis=1)
    return out


def _episodes(per_ret: Int, dates: list[str], names: tuple[str, ...]) -> list[Episode]:
    """Collapse per-return labels into dated stretches."""
    out: list[Episode] = []
    if per_ret.size == 0:
        return out
    start = 0
    for i in range(1, per_ret.size + 1):
        if i < per_ret.size and per_ret[i] == per_ret[start]:
            continue
        lbl = int(per_ret[start])
        if lbl >= 0:
            out.append(
                Episode(
                    label=lbl,
                    name=names[lbl] if lbl < len(names) else f"regime {lbl + 1}",
                    start=dates[start + 1],
                    end=dates[min(i, len(dates) - 1)],
                    days=i - start,
                )
            )
        start = i
    return out
