"""Price paths whose regimes are known, because we planted them.

The problem this solves is stated plainly in the paper (their §3.3): on real
market data nobody can say what the correct clustering *was*, so an accuracy
figure cannot exist. Any number you quote about a regime detector on real
prices is either a restatement of the detector's own opinion or a person
pointing at a chart.

So the detector gets tested somewhere the answer is known. Two generators,
both from the paper, with regime intervals switched on at chosen times:

    gBm     log-returns are Gaussian. The easy case, and the one where a
            moment-based rule should do well — if a method loses here it is
            broken, and this is the regression test that would catch it.

    Merton  jump diffusion: Gaussian diffusion plus Poisson jumps. The case
            that matters, because it is the one real equity returns resemble,
            and the one where the paper's moment benchmark falls from 93% to
            67% overall and to 27% on the regime changes themselves.

These are fixtures, not simulations of anything. Nothing here is fitted to a
real company and nothing here should ever reach a user-facing number; it
exists so ``tests/test_regimes.py`` can assert a floor on accuracy that a
future change has to clear.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Float = NDArray[np.float64]
Bool = NDArray[np.bool_]

TRADING_DAYS = 252


@dataclass(frozen=True)
class SyntheticPath:
    """A generated path and the regime mask that produced it."""

    closes: Float
    rets: Float
    #: True where the *return* at that index was drawn under the stressed
    #: parameters. One shorter than ``closes``, and aligned to it from index 1.
    stressed: Bool
    switches: list[tuple[int, int]]

    @property
    def stress_share(self) -> float:
        return float(self.stressed.mean())


def _switch_mask(n: int, runs: int, length: int, rng: np.random.Generator) -> Bool:
    """``runs`` non-overlapping stressed stretches of ``length`` steps."""
    mask = np.zeros(n, dtype=bool)
    if runs <= 0 or length <= 0:
        return mask
    slots = n // max(runs, 1)
    if slots <= length:
        raise ValueError(f"{runs} runs of {length} do not fit in {n} steps")
    for i in range(runs):
        lo = i * slots
        hi = lo + slots - length
        start = int(rng.integers(lo, max(lo + 1, hi)))
        mask[start : start + length] = True
    return mask


def _runs_of(mask: Bool) -> list[tuple[int, int]]:
    """``[start, end)`` of each True run, for plotting and for reporting."""
    out: list[tuple[int, int]] = []
    start: int | None = None
    for i, on in enumerate(mask):
        if on and start is None:
            start = i
        elif not on and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def gbm(
    n: int = 2520,
    *,
    calm: tuple[float, float] = (0.08, 0.16),
    stressed: tuple[float, float] = (-0.10, 0.36),
    runs: int = 6,
    length: int = 126,
    seed: int = 0,
) -> SyntheticPath:
    """Geometric Brownian motion that switches parameters (their §3.3.1).

    ``calm`` and ``stressed`` are ``(mu, sigma)`` in annual terms. Defaults are
    a daily analogue of the paper's hourly (0.02, 0.2) / (-0.02, 0.3): stretches
    of roughly half a year, six of them over ten years.
    """
    rng = np.random.default_rng(seed)
    mask = _switch_mask(n, runs, length, rng)
    dt = 1.0 / TRADING_DAYS

    mu = np.where(mask, stressed[0], calm[0])
    sd = np.where(mask, stressed[1], calm[1])
    rets = (mu - 0.5 * sd**2) * dt + sd * np.sqrt(dt) * rng.standard_normal(n)

    closes = np.concatenate([[100.0], 100.0 * np.exp(np.cumsum(rets))])
    return SyntheticPath(closes=closes, rets=rets, stressed=mask, switches=_runs_of(mask))


def merton(
    n: int = 2520,
    *,
    calm: tuple[float, float, float, float, float] = (0.08, 0.16, 5.0, 0.02, 0.05),
    stressed: tuple[float, float, float, float, float] = (-0.10, 0.32, 40.0, -0.04, 0.12),
    runs: int = 6,
    length: int = 126,
    seed: int = 0,
) -> SyntheticPath:
    """Merton jump diffusion that switches parameters (their §3.3.2).

    Parameters are ``(mu, sigma, lambda, gamma, delta)``: drift, diffusive
    volatility, jump intensity per year, and the mean and standard deviation
    of the log jump size. The stressed leg jumps eight times as often and
    downwards on average, which is the asymmetry that breaks a variance-only
    rule — variance is blind to the sign.
    """
    rng = np.random.default_rng(seed)
    mask = _switch_mask(n, runs, length, rng)
    dt = 1.0 / TRADING_DAYS

    mu = np.where(mask, stressed[0], calm[0])
    sd = np.where(mask, stressed[1], calm[1])
    lam = np.where(mask, stressed[2], calm[2])
    gam = np.where(mask, stressed[3], calm[3])
    dlt = np.where(mask, stressed[4], calm[4])

    diffusive = (mu - 0.5 * sd**2) * dt + sd * np.sqrt(dt) * rng.standard_normal(n)
    counts = rng.poisson(lam * dt)
    # Sum of `counts` iid Normal(gamma, delta^2) draws is Normal(c*gamma, c*delta^2).
    jumps = counts * gam + np.sqrt(counts) * dlt * rng.standard_normal(n)
    rets = diffusive + jumps

    closes = np.concatenate([[100.0], 100.0 * np.exp(np.cumsum(rets))])
    return SyntheticPath(closes=closes, rets=rets, stressed=mask, switches=_runs_of(mask))


# ── scoring against the planted truth ──────────────────────────────────────


@dataclass(frozen=True)
class Accuracy:
    """Their Defs. 3.7 — eqs. 31, 32, 33.

    ``regime_on`` is the one that matters and the one an overall figure hides.
    A detector that never fires scores 100% off-regime and, weighted by how
    rare stress is, can still post a respectable total — the paper's HMM row
    does exactly this, at 99.87% off and 0.66% on.
    """

    total: float
    regime_on: float
    regime_off: float


def score(predicted_stress: Bool, truth: Bool) -> Accuracy:
    """Accuracy of a per-return stress flag against the planted mask."""
    predicted_stress = np.asarray(predicted_stress, dtype=bool)
    truth = np.asarray(truth, dtype=bool)
    if predicted_stress.shape != truth.shape:
        raise ValueError(f"{predicted_stress.shape} predictions for {truth.shape} truth")
    on = truth.sum()
    off = (~truth).sum()
    return Accuracy(
        total=float((predicted_stress == truth).mean()),
        regime_on=float(predicted_stress[truth].mean()) if on else float("nan"),
        regime_off=float((~predicted_stress[~truth]).mean()) if off else float("nan"),
    )
