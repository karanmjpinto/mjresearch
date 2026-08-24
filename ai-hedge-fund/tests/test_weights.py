"""Portfolio weighting invariants.

These are the numbers a user actually acts on — the allocation across a basket —
so the properties asserted here are the ones whose violation would be invisible.
A weight vector that is subtly wrong still sums to 1 and still renders as a
neat pie chart; nothing downstream can tell. Hence property tests over generated
returns rather than a handful of golden vectors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hedge_fund.quant.portfolio.weights import METHOD_REGISTRY, optimize_weights

METHODS = sorted(METHOD_REGISTRY)

# The mean-variance method runs a constrained SLSQP solve, so examples are kept
# few and small and the per-example deadline is lifted; timing is not the thing
# under test.
SLOW = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

# Every method but one is closed-form and reproduces bit-for-bit. `mean_variance`
# runs an SLSQP solve to ftol=1e-8, so reordering the basket perturbs the iterate
# path and lands a fraction under 1e-7 away. That tolerance is the solver's, not
# a slack we chose: asserting tighter would be asserting a guarantee scipy does
# not make, and the test would fail on an unrelated day.
#
# HRP is held to the exact bound deliberately. It used to fail this test by up to
# four percentage points of weight, because scipy's linkage could mirror a
# subtree and move where the recursive bisection split. Anything above numerical
# noise here is that bug returning, not a tolerance to widen.
_ATOL = {m: 1e-9 for m in METHODS}
_ATOL["mean_variance"] = 1e-6


def _returns(draw_seed: int, periods: int, assets: int, scale: float = 0.01) -> pd.DataFrame:
    rng = np.random.default_rng(draw_seed)
    cols = [f"A{i}" for i in range(assets)]
    return pd.DataFrame(rng.normal(0.0, scale, size=(periods, assets)), columns=cols)


# ----------------------------------------------------------------------
# Universal invariants — must hold for every method, on every input
# ----------------------------------------------------------------------


@SLOW
@given(
    method=st.sampled_from(METHODS),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    periods=st.integers(min_value=20, max_value=90),
    assets=st.integers(min_value=1, max_value=6),
)
def test_weights_are_a_long_only_distribution(method, seed, periods, assets):
    w = optimize_weights(method, _returns(seed, periods, assets))

    assert len(w) == assets, "one weight per asset"
    assert np.isfinite(w).all(), "no NaN or inf reaches the caller"
    assert (w >= 0).all(), "long-only: no method may short"
    assert w.sum() == pytest.approx(1.0, abs=1e-9), "fully invested"


@SLOW
@given(
    method=st.sampled_from(METHODS),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    assets=st.integers(min_value=2, max_value=6),
)
def test_weights_do_not_depend_on_column_order(method, seed, assets):
    """Relabelling the basket must not reallocate it.

    Column order is an artifact of however the caller assembled the request. If
    it changed the answer, two identical portfolios would optimize differently
    depending on the order a UI happened to send them in.
    """
    df = _returns(seed, 120, assets)
    order = list(df.columns)
    shuffled = list(np.random.default_rng(seed + 1).permutation(order))

    base = pd.Series(optimize_weights(method, df), index=order)
    perm = pd.Series(optimize_weights(method, df[shuffled]), index=shuffled)

    np.testing.assert_allclose(base.values, perm.reindex(order).values, atol=_ATOL[method])


@pytest.mark.parametrize("method", METHODS)
def test_single_asset_gets_everything(method):
    df = _returns(3, 60, 1)
    np.testing.assert_allclose(optimize_weights(method, df), [1.0])


@pytest.mark.parametrize("method", METHODS)
def test_constant_series_does_not_produce_nan(method):
    """A halted name, or a gap filled with zeros, must not poison the basket.

    Regression: HRP divided by a zero variance, and the resulting nan failed the
    caller's `> 0` guard, silently collapsing the bisection to a 50/50 split that
    still summed to 1 and looked deliberate.
    """
    df = _returns(5, 80, 4)
    df["A2"] = 0.0

    w = optimize_weights(method, df)
    assert np.isfinite(w).all()
    assert w.sum() == pytest.approx(1.0, abs=1e-9)
    assert (w >= 0).all()


def test_unknown_method_is_rejected_by_name():
    with pytest.raises(KeyError, match="Unknown method"):
        optimize_weights("no_such_method", _returns(1, 30, 3))


# ----------------------------------------------------------------------
# Method-specific behaviour — the thing each method claims to do
# ----------------------------------------------------------------------


def test_equal_weight_is_uniform():
    w = optimize_weights("equal_weight", _returns(11, 60, 5))
    np.testing.assert_allclose(w, np.full(5, 0.2))


def test_inverse_vol_prefers_the_calmer_asset():
    """The defining property: weight moves opposite to volatility."""
    rng = np.random.default_rng(21)
    quiet = rng.normal(0, 0.002, 400)
    loud = rng.normal(0, 0.020, 400)
    df = pd.DataFrame({"QUIET": quiet, "LOUD": loud})

    w = pd.Series(optimize_weights("inverse_vol", df), index=df.columns)
    assert w["QUIET"] > w["LOUD"]
    # Vol differs by ~10x, so the weight ratio should be of that order, not marginal.
    assert w["QUIET"] / w["LOUD"] > 3.0


def test_conviction_weighting_is_monotone_in_conviction():
    df = _returns(31, 80, 3)
    convictions = {"A0": 90.0, "A1": 70.0, "A2": 50.0}

    w = pd.Series(optimize_weights("conviction_weighted", df, convictions), index=df.columns)
    assert w["A0"] > w["A1"] > w["A2"]


def test_conviction_below_the_buy_threshold_is_excluded():
    """Sub-40 conviction is documented as HOLD/neutral and must get nothing."""
    df = _returns(33, 80, 3)
    convictions = {"A0": 80.0, "A1": 39.0, "A2": 60.0}

    w = pd.Series(optimize_weights("conviction_weighted", df, convictions), index=df.columns)
    assert w["A1"] == 0.0
    assert w["A0"] > 0 and w["A2"] > 0
    assert w.sum() == pytest.approx(1.0)


def test_conviction_falls_back_to_equal_when_nothing_qualifies():
    """Every name below the threshold must not divide by zero, or concentrate."""
    df = _returns(35, 60, 4)
    w = optimize_weights("conviction_weighted", df, {c: 10.0 for c in df.columns})
    np.testing.assert_allclose(w, np.full(4, 0.25))


def test_conviction_without_scores_is_equal_weight():
    df = _returns(37, 60, 4)
    np.testing.assert_allclose(
        optimize_weights("conviction_weighted", df, None),
        optimize_weights("equal_weight", df),
    )


def test_hrp_spreads_across_correlated_blocks():
    """HRP should not pile into one block of near-identical names.

    Three assets that move together plus one independent name: the diversifier
    should not be starved the way naive inverse-variance would starve it.
    """
    rng = np.random.default_rng(41)
    common = rng.normal(0, 0.01, 500)
    df = pd.DataFrame(
        {
            "B1": common + rng.normal(0, 0.001, 500),
            "B2": common + rng.normal(0, 0.001, 500),
            "B3": common + rng.normal(0, 0.001, 500),
            "SOLO": rng.normal(0, 0.01, 500),
        }
    )

    w = pd.Series(optimize_weights("hrp", df), index=df.columns)
    block = w[["B1", "B2", "B3"]].sum()
    assert w["SOLO"] > block / 3, "the independent name beats the average block member"
    assert w.sum() == pytest.approx(1.0)


def test_mean_variance_stays_long_only_under_negative_drift():
    """Losers get zero, not a short."""
    rng = np.random.default_rng(51)
    df = pd.DataFrame(
        {
            "UP": rng.normal(0.0015, 0.01, 300),
            "DOWN": rng.normal(-0.0015, 0.01, 300),
        }
    )

    w = pd.Series(optimize_weights("mean_variance", df), index=df.columns)
    assert (w >= 0).all()
    assert w.sum() == pytest.approx(1.0, abs=1e-9)
    assert w["UP"] > w["DOWN"]
