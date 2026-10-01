"""Hidden Markov models — the part of a regime the clustering cannot see.

Jurafsky and Martin, *Speech and Language Processing* (3rd ed.), Appendix A:
*Hidden Markov Models*. The algorithms are theirs — Forward (their Fig. A.7),
Viterbi (their Fig. A.9) and Forward-Backward, or Baum-Welch (their Fig. A.14)
— applied to daily log-returns with Gaussian emissions in place of a discrete
symbol table. The hidden states are the regimes; the observations are the
returns; nobody labelled either, which is the unsupervised case the chapter is
about.

WHY THIS SITS BESIDE THE CLUSTERING RATHER THAN REPLACING IT

:mod:`.wasserstein` closes with the sentence this module exists to answer:

    It also labels rather than predicts. Which regime you are in now says
    nothing here about which comes next.

That is not a gap in the implementation, it is what clustering *is*. WK-means
treats the windows as an unordered bag — shuffle the history and the labels
come back identical. So every question a reader asks next is unanswerable in
that model, because all of them are questions about the order: how long do
these stretches run, does turbulence follow turbulence, what are the odds this
one is over.

The hidden chain is exactly that missing object. The transition matrix A is
*fitted*, not assumed, so persistence (a_jj), expected run length (1/(1-a_jj))
and tomorrow's state distribution all fall out of something the data chose.
That is the whole reason this module is here.

AND WHY IT IS NOT AN UPGRADE

As a *detector* it is worse, and this package already said so before the module
existed: :class:`.synthetic.Accuracy` records the Horvath paper's HMM row at
99.87% off-regime and 0.66% on — a model that scores well overall by almost
never calling stress. The Gaussian emission is why. Equity returns jump, a
Gaussian cannot, and maximum likelihood would rather widen one state's sigma to
cover the jumps than spend a transition switching to the other. So both
labellings are scored on the same windows with the same kernel
(:mod:`.mmd`) and reported together, and ``tests/test_regimes.py`` pins the
ordering so that no later change can quietly promote this one.

Read it as: the clustering says *where you are*, this says *how it moves*.

ONE DELIBERATE DEPARTURE FROM THE CHAPTER

The chapter's pseudocode multiplies probabilities directly. On its three-day
ice-cream example that is exact; on 2,500 daily returns every forward value
underflows to zero within about fifty steps and the model reports a likelihood
of -inf for all parameters, which EM then cannot climb.

So forward and backward run scaled, the standard fix: each column is
normalised to sum to one and the normaliser c_t is kept, giving
``log P(O|lambda) = -sum_t log c_t`` (plus the per-column constant described in
:func:`emissions`). The recursions are otherwise line for line the chapter's,
and :func:`unscale` recovers the raw alpha values the chapter prints, which is
how the textbook figures are asserted in the tests.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from hedge_fund.regimes.wasserstein import RegimeError

Float = NDArray[np.float64]
Int = NDArray[np.int64]

#: A floor on a fitted state's standard deviation. Without one, a Gaussian
#: emission is free to collapse onto a single observation, where the density —
#: and so the likelihood EM is climbing — runs to infinity. That degenerate
#: optimum is a real maximum, not a bug, and the floor is the usual guard.
MIN_SIGMA = 1e-8

#: Transitions are floored before renormalising so no arc ever becomes exactly
#: impossible. A zero in A is permanent — nothing in the M-step can ever raise
#: it again — so one unlucky iteration would otherwise weld two regimes
#: together for the rest of the fit.
FLOOR = 1e-12

#: Daily returns, so a regime that dissolves in under a week is a data artefact
#: rather than a regime. Reported, not enforced: see :attr:`Fit.expected_days`.
TRADING_DAYS = 252


# ── emissions ──────────────────────────────────────────────────────────────


def emissions(obs: Float, means: Float, sigmas: Float) -> tuple[Float, Float]:
    """Gaussian ``b_j(o_t)`` as a ``(T, k)`` matrix, row-rescaled.

    Returns the likelihoods with each row divided by its own largest entry,
    and the log of the divisors. Row scaling is free: it multiplies every path
    through the trellis by the same constant, so gamma, xi and the Viterbi path
    are untouched and the log-likelihood only needs the constants added back.

    Doing it inside the emission rather than inside the recursion is what keeps
    the algorithms below readable as the chapter's.
    """
    obs = np.asarray(obs, dtype=np.float64)
    z = (obs[:, None] - means[None, :]) / sigmas[None, :]
    logb = -0.5 * z * z - np.log(sigmas)[None, :] - 0.5 * np.log(2.0 * np.pi)
    shift = logb.max(axis=1)
    return np.exp(logb - shift[:, None]), shift


# ── A.3 the forward algorithm (their Fig. A.7) ─────────────────────────────


@dataclass(frozen=True)
class Forward:
    """The scaled forward pass.

    ``alpha`` holds ``P(q_t = j | o_1..o_t)`` — each column sums to one, which
    is what the scaling buys. ``scale`` holds the normalisers c_t, and
    :func:`unscale` turns the pair back into the chapter's raw alpha.
    """

    alpha: Float
    scale: Float
    loglik: float


def forward(b: Float, a: Float, pi: Float, shift: Float | None = None) -> Forward:
    """Their eqs. A.11-A.12, with scaling.

    ``b`` is the ``(T, k)`` emission matrix, ``a`` the ``(k, k)`` transitions
    and ``pi`` the start distribution. ``shift`` is the log constant removed by
    :func:`emissions`; pass ``None`` when ``b`` holds true likelihoods, as it
    does for a discrete model.
    """
    b = np.asarray(b, dtype=np.float64)
    t_max, k = b.shape
    alpha = np.empty((t_max, k))
    scale = np.empty(t_max)

    cur = pi * b[0]  # initialisation: alpha_1(j) = pi_j b_j(o_1)
    total = cur.sum()
    if total <= 0:
        raise RegimeError("the first observation has zero likelihood under every state")
    scale[0] = 1.0 / total
    alpha[0] = cur * scale[0]

    for t in range(1, t_max):
        # recursion: alpha_t(j) = sum_i alpha_{t-1}(i) a_ij b_j(o_t)
        cur = (alpha[t - 1] @ a) * b[t]
        total = cur.sum()
        if total <= 0:
            raise RegimeError(f"observation {t} has zero likelihood under every state")
        scale[t] = 1.0 / total
        alpha[t] = cur * scale[t]

    # termination: the chapter sums alpha_T; scaled, that sum is one and the
    # likelihood lives entirely in the normalisers.
    loglik = float(-np.log(scale).sum())
    if shift is not None:
        loglik += float(np.sum(shift))
    return Forward(alpha=alpha, scale=scale, loglik=loglik)


def unscale(alpha: Float, scale: Float) -> Float:
    """The chapter's raw ``alpha_t(j)``, recovered from the scaled pass.

    Exists for the tests: it is the only way to check this implementation
    against the numbers printed in their Fig. A.5, and it overflows on any
    real series, which is the point of the scaling it undoes.
    """
    return np.asarray(alpha) / np.cumprod(scale)[:, None]


# ── the backward pass (their eq. A.15) ─────────────────────────────────────


def backward(b: Float, a: Float, scale: Float) -> Float:
    """Their beta recursion, scaled by the forward pass's own c_t.

    Sharing the normalisers is what makes gamma and xi come out already
    divided by ``P(O|lambda)``, so the chapter's eqs. A.22 and A.27 need no
    separate division.
    """
    b = np.asarray(b, dtype=np.float64)
    t_max, k = b.shape
    beta = np.empty((t_max, k))
    beta[-1] = scale[-1]  # initialisation: beta_T(i) = 1, scaled
    for t in range(t_max - 2, -1, -1):
        beta[t] = (a @ (b[t + 1] * beta[t + 1])) * scale[t]
    return beta


# ── A.5 the E-step (their Fig. A.14) ───────────────────────────────────────


@dataclass(frozen=True)
class Estep:
    """Expected counts for one pass of Baum-Welch.

    ``gamma`` is their eq. A.27, ``P(q_t = j | O, lambda)`` — the posterior
    probability of each state on each day, and the honest answer to "how sure
    are we about today". ``xi`` is their eq. A.22 already summed over t, which
    is the numerator of eq. A.23.
    """

    gamma: Float
    xi: Float
    loglik: float


def estep(b: Float, a: Float, pi: Float, shift: Float | None = None) -> Estep:
    """Forward, backward, and the two expected counts."""
    fwd = forward(b, a, pi, shift)
    beta = backward(b, a, fwd.scale)

    gamma = fwd.alpha * beta
    gamma /= gamma.sum(axis=1, keepdims=True)

    # xi_t(i,j) = alpha_t(i) a_ij b_j(o_{t+1}) beta_{t+1}(j); under the shared
    # scaling each t already sums to one, so summing over t needs no division.
    # One einsum rather than a loop over T, which is most of the fit's cost.
    xi = a * np.einsum("ti,tj->ij", fwd.alpha[:-1], b[1:] * beta[1:])
    return Estep(gamma=gamma, xi=xi, loglik=fwd.loglik)


# ── A.4 decoding (their Fig. A.9) ──────────────────────────────────────────


def viterbi(b: Float, a: Float, pi: Float) -> tuple[Int, float]:
    """The single most probable state path, and its log probability.

    Their eqs. A.13-A.14 in logs: the recursion is a product of up to 2,500
    terms, so the max is taken over sums of logs rather than over products
    that would underflow long before the path ended.

    Decoding matters here for a reason the per-window vote in :mod:`.detect`
    cannot reproduce. A vote picks each day's label independently and can
    hand back a path the model thinks is impossible — a one-day switch under
    a transition matrix that says switches are rare. Viterbi maximises over
    whole paths, so the sequence it returns is one the fitted chain would
    actually produce.
    """
    with np.errstate(divide="ignore"):
        logb = np.log(np.asarray(b, dtype=np.float64))
        loga = np.log(np.asarray(a, dtype=np.float64))
        logpi = np.log(np.asarray(pi, dtype=np.float64))

    t_max, k = logb.shape
    v = np.empty((t_max, k))
    back = np.zeros((t_max, k), dtype=np.int64)

    v[0] = logpi + logb[0]
    for t in range(1, t_max):
        cand = v[t - 1][:, None] + loga  # (i, j)
        back[t] = cand.argmax(axis=0)
        v[t] = cand.max(axis=0) + logb[t]

    path = np.empty(t_max, dtype=np.int64)
    path[-1] = int(v[-1].argmax())
    for t in range(t_max - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path, float(v[-1].max())


# ── the fitted model ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Fit:
    """A trained Gaussian HMM over one return series.

    States are ordered calm first — ascending ``sigmas`` — matching
    :func:`.wasserstein._order_by_dispersion`, so label 0 means the same thing
    in both methods and a colour or a stored label survives the comparison.
    """

    start: Float  # pi
    transition: Float  # A
    means: Float
    sigmas: Float
    gamma: Float  # (T, k) per-day posterior
    path: Int  # (T,) Viterbi
    loglik: float
    iterations: int
    converged: bool

    @property
    def k(self) -> int:
        return int(self.means.size)

    @property
    def persistence(self) -> Float:
        """``a_jj``: the chance a state is followed by itself tomorrow."""
        return np.diag(self.transition).copy()

    @property
    def expected_days(self) -> Float:
        """Mean run length of each state, ``1 / (1 - a_jj)``.

        The geometric mean of the duration distribution a first-order chain
        implies. It is a property of the fitted matrix, not a measurement of
        the observed episodes, and the two disagreeing is informative: a chain
        that implies 8-day regimes on a path full of 60-day ones is telling you
        the Markov assumption (their eq. A.4) does not hold on this name.
        """
        stay = np.clip(self.persistence, 0.0, 1.0 - 1e-12)
        return 1.0 / (1.0 - stay)

    @property
    def next_day(self) -> Float:
        """Tomorrow's state distribution: the last posterior pushed through A.

        One step of the chain from where the model believes it is today. It is
        a description of how *this fitted history* switched, not a forecast:
        the parameters were estimated using the whole series, the end of it
        included, so a walk-forward user must refit. See ``CAVEATS`` in
        :mod:`.detect`.

        Read the last few days' ``gamma`` before leaning on it. The backward
        pass starts from ``beta_T = 1`` — there is no future evidence to anchor
        the end of the series — so the final marginals are the least certain in
        the whole fit and can drift away from the Viterbi path, which still has
        the transition penalty holding it in place. When the two disagree at
        the end, that disagreement *is* the uncertainty, and :mod:`.detect`
        reports both rather than picking one.
        """
        return np.asarray(self.gamma[-1] @ self.transition, dtype=np.float64)

    @property
    def bic(self) -> float:
        """Bayesian information criterion — lower is better.

        A k-state Gaussian HMM has k(k-1) free transitions, k-1 free start
        probabilities and 2k emission parameters. Reported because k is chosen
        by hand here, and a reader comparing two choices of k should not have
        to compare raw likelihoods, which always favour the larger model.
        """
        k = self.k
        params = k * (k - 1) + (k - 1) + 2 * k
        n = int(self.gamma.shape[0])
        return float(params * np.log(n) - 2.0 * self.loglik)


def _seed_params(
    rets: Float, k: int, rng: np.random.Generator, jitter: bool
) -> tuple[Float, Float, Float, Float]:
    """Starting parameters for one EM run.

    The chapter is blunt that "in practice the initial conditions are very
    important", and for this problem the important one is the diagonal of A.
    Started uniform, EM on daily returns reliably finds the solution where the
    chain switches almost every day and the two states are two halves of one
    noise distribution — a perfectly good local optimum that means nothing. A
    persistent prior starts it in the basin where states are stretches.

    The emissions are seeded by splitting the series on local dispersion, so
    run zero is deterministic and the restarts jitter around it.
    """
    span = max(5, rets.size // 100)
    local = np.convolve(np.abs(rets - float(np.median(rets))), np.ones(span) / span, mode="same")
    cuts = np.quantile(local, np.linspace(0.0, 1.0, k + 1)[1:-1])
    group = np.digitize(local, cuts)

    means = np.empty(k)
    sigmas = np.empty(k)
    for j in range(k):
        member = rets[group == j]
        if member.size < 2:
            member = rets
        means[j] = float(member.mean())
        sigmas[j] = max(float(member.std()), MIN_SIGMA)
    if jitter:
        means = means + 0.25 * sigmas * rng.standard_normal(k)
        sigmas = sigmas * np.exp(0.25 * rng.standard_normal(k))
        sigmas = np.maximum(sigmas, MIN_SIGMA)

    stay = 0.94
    a = np.full((k, k), (1.0 - stay) / max(k - 1, 1))
    np.fill_diagonal(a, stay)
    a /= a.sum(axis=1, keepdims=True)
    return np.full(k, 1.0 / k), a, means, sigmas


def _mstep(obs: Float, e: Estep) -> tuple[Float, Float, Float, Float]:
    """Their eq. A.23 for A, and its Gaussian analogue for the emissions.

    Where the chapter counts symbols (eq. A.28), a continuous emission takes
    the gamma-weighted mean and variance instead — the same expected-count
    argument, with an integral where the sum over the vocabulary was.
    """
    weight = e.gamma.sum(axis=0)
    weight = np.maximum(weight, FLOOR)
    means = (e.gamma * obs[:, None]).sum(axis=0) / weight
    var = (e.gamma * (obs[:, None] - means[None, :]) ** 2).sum(axis=0) / weight
    sigmas = np.sqrt(np.maximum(var, MIN_SIGMA**2))

    a = np.maximum(e.xi, FLOOR)
    a /= a.sum(axis=1, keepdims=True)
    pi = np.maximum(e.gamma[0], FLOOR)
    pi /= pi.sum()
    return pi, a, means, sigmas


def _order_calm_first(
    pi: Float, a: Float, means: Float, sigmas: Float, gamma: Float
) -> tuple[Float, Float, Float, Float, Float]:
    """Relabel states by ascending sigma, permuting A on both axes."""
    order = np.argsort(sigmas, kind="stable")
    return pi[order], a[np.ix_(order, order)], means[order], sigmas[order], gamma[:, order]


def fit(
    rets: Float,
    k: int = 2,
    *,
    seed: int = 0,
    max_iter: int = 60,
    tol: float = 1e-7,
    restarts: int = 3,
) -> Fit:
    """Baum-Welch on daily log-returns (their Fig. A.14), then Viterbi.

    Deterministic given ``seed``. ``restarts`` runs EM from different starts
    and keeps the highest likelihood, because EM climbs to a local optimum and
    a single start cannot tell you which one it found.

    ``tol`` is a relative improvement in log-likelihood; EM's monotonicity
    guarantee makes that a safe stopping rule.
    """
    rets = np.asarray(rets, dtype=np.float64)
    rets = rets[np.isfinite(rets)]
    if rets.size < 30 * k:
        raise RegimeError(
            f"{rets.size} returns cannot support a {k}-state model; "
            "ask for more history or fewer states"
        )
    if k < 2:
        raise RegimeError(f"k must be at least 2, got {k}")
    if float(rets.std()) <= 0:
        raise RegimeError("every return is identical — there is nothing to model")

    best: Fit | None = None
    for r in range(max(1, restarts)):
        got = _fit_once(rets, k, np.random.default_rng(seed + r), max_iter, tol, jitter=r > 0)
        if got is None:
            continue
        if best is None or got.loglik > best.loglik:
            best = got
    if best is None:
        raise RegimeError("every EM run collapsed — the returns will not support this many states")
    return best


def _fit_once(
    rets: Float,
    k: int,
    rng: np.random.Generator,
    max_iter: int,
    tol: float,
    *,
    jitter: bool,
) -> Fit | None:
    """One EM run. ``None`` if a state emptied or the likelihood went nowhere."""
    pi, a, means, sigmas = _seed_params(rets, k, rng, jitter)
    prev = -np.inf
    e: Estep | None = None
    used = 0
    converged = False

    for it in range(1, max_iter + 1):
        used = it
        b, shift = emissions(rets, means, sigmas)
        try:
            e = estep(b, a, pi, shift)
        except RegimeError:
            return None
        if not np.isfinite(e.loglik):
            return None
        if e.loglik < prev - 1e-6:  # EM cannot descend; if it did, stop and keep the last good fit
            break
        if np.isfinite(prev) and e.loglik - prev <= tol * abs(prev):
            converged = True
            pi, a, means, sigmas = _mstep(rets, e)
            break
        prev = e.loglik
        pi, a, means, sigmas = _mstep(rets, e)

    b, shift = emissions(rets, means, sigmas)
    try:
        e = estep(b, a, pi, shift)
    except RegimeError:
        return None
    path, _ = viterbi(b, a, pi)
    if np.unique(path).size < k:
        # A state nothing is ever assigned to is not a regime; report the
        # failure rather than returning a k that the labels do not support.
        return None

    # Order first, then decode: the path has to index the states the caller
    # will be shown, and `_order_calm_first` renumbers them.
    pi, a, means, sigmas, gamma = _order_calm_first(pi, a, means, sigmas, e.gamma)
    b, _ = emissions(rets, means, sigmas)
    path, _ = viterbi(b, a, pi)

    return Fit(
        start=pi,
        transition=a,
        means=means,
        sigmas=sigmas,
        gamma=gamma,
        path=path,
        loglik=float(e.loglik),
        iterations=used,
        converged=converged,
    )
