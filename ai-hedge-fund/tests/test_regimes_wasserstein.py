"""The Wasserstein half: the closed forms, the fit, the score, and the wiring.

Split from ``test_regimes.py`` deliberately. That file guards the *comparison*
between the clustering and the hidden chain — which detector wins on which
kind of path. This one guards the machinery underneath: that W1 really is W1,
that a barycentre really is a median, that the fit numbers its clusters the
same way twice, that the MMD score can tell a real split from a shuffled one,
and that the metric and the route hand the rest of the app what they promise.

What these catch is invisible on a chart. A barycentre computed as a mean
still draws a plausible curve. Clusters numbered by the seeding still colour
the page, just differently on every run. A labelling that cut one population
in half still produces confident episodes with dates on them. None of it
raises.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy.stats import wasserstein_distance

from hedge_fund.api.main import app
from hedge_fund.plan.registry import get_metric
from hedge_fund.plan.types import MetricError
from hedge_fund.regimes import analyse, detect, mmd
from hedge_fund.regimes import synthetic as syn
from hedge_fund.regimes import wasserstein as wk

client = TestClient(app)


def _dates(n: int) -> list[str]:
    """Weekday dates, so an episode's span reads like a real trading calendar."""
    out: list[str] = []
    d = dt.date(2010, 1, 4)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _two_regime_windows(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.vstack([rng.normal(0.0005, 0.008, (40, 50)), rng.normal(-0.001, 0.030, (20, 50))])


# ── the closed forms ──────────────────────────────────────────────────────


def test_w1_matches_scipy():
    """Eq. 21 is only valid on sorted, equal-length samples — check it is."""
    rng = np.random.default_rng(0)
    for _ in range(20):
        a = rng.normal(0, 0.01, 64)
        b = rng.normal(0.002, 0.03, 64)
        assert wk.w1(np.sort(a), np.sort(b)) == pytest.approx(
            wasserstein_distance(a, b), rel=1e-9
        )


def test_w1_is_a_metric_on_these_samples():
    rng = np.random.default_rng(1)
    a, b, c = (np.sort(rng.normal(0, s, 40)) for s in (0.01, 0.02, 0.05))
    assert wk.w1(a, a) == 0.0
    assert wk.w1(a, b) == pytest.approx(wk.w1(b, a))
    assert wk.w1(a, c) <= wk.w1(a, b) + wk.w1(b, c) + 1e-12


def test_barycentre_is_the_pointwise_median_of_order_statistics():
    """Prop. 2.6 — and the reason one crash window cannot move a centroid."""
    wins = np.sort(np.array([[1.0, 2, 3], [1.5, 2.5, 3.5], [1.2, 2.2, 3.2]]), axis=1)
    assert wk.barycentre(wins).tolist() == [1.2, 2.2, 3.2]

    calm = np.sort(np.random.default_rng(2).normal(0, 0.01, (41, 30)), axis=1)
    poisoned = calm.copy()
    poisoned[7] = -0.5

    median_shift = np.abs(wk.barycentre(poisoned) - wk.barycentre(calm)).max()
    mean_shift = np.abs(poisoned.mean(axis=0) - calm.mean(axis=0)).max()

    # The median does not move by nothing — dropping one window from above the
    # middle shifts each order statistic by one rank, which is a property of
    # the sample size and not of how bad the outlier was. What matters is that
    # it cannot scale with the outlier, and a mean can: -0.5 spread over 41
    # windows drags every mean atom by roughly 0.012 on its own.
    assert median_shift < mean_shift / 10, f"median moved {median_shift}, mean {mean_shift}"
    assert mean_shift > 1e-3, "the poisoned window should wreck a mean centroid"


# ── the lift ──────────────────────────────────────────────────────────────


def test_windows_step_by_h1_minus_h2_and_cover_the_series():
    w = wk.windows(np.arange(20, dtype=float), h1=5, h2=3)  # step 2
    assert w.shape == (8, 5)
    assert w[0].tolist() == [0, 1, 2, 3, 4]
    assert w[1].tolist() == [2, 3, 4, 5, 6]
    assert wk.window_spans(8, 5, 3)[1] == (2, 7)


def test_disjoint_windows_when_there_is_no_overlap():
    w = wk.windows(np.arange(12, dtype=float), h1=4, h2=0)
    assert w.shape == (3, 4)
    assert w[1].tolist() == [4, 5, 6, 7]


@pytest.mark.parametrize("h1,h2", [(1, 0), (5, 5), (5, 6), (5, -1)])
def test_impossible_window_parameters_are_refused(h1: int, h2: int):
    with pytest.raises(wk.RegimeError):
        wk.windows(np.arange(50, dtype=float), h1=h1, h2=h2)


def test_too_little_history_says_so_rather_than_returning_nothing():
    with pytest.raises(wk.RegimeError, match="cannot fill"):
        wk.windows(np.arange(10, dtype=float), h1=30, h2=20)


def test_non_finite_steps_are_dropped_not_propagated():
    """A zero close makes a log-return -inf, which would poison every window."""
    rets = wk.log_returns(np.array([100.0, 101.0, 0.0, 102.0, 103.0]))
    assert np.isfinite(rets).all()



# ── the fit ───────────────────────────────────────────────────────────────


def test_fit_is_deterministic_given_a_seed():
    wins = _two_regime_windows()
    a, b = wk.wk_means(wins, k=2, seed=7), wk.wk_means(wins, k=2, seed=7)
    assert a.labels.tolist() == b.labels.tolist()
    assert np.allclose(a.centroids, b.centroids)


def test_cluster_zero_is_always_the_calm_one():
    """The invariant every colour, stored label and eval downstream rests on.

    Without it k-means numbers its clusters by whatever the seeding did, and
    "cluster 1" means a different thing on each run and each ticker.
    """
    wins = _two_regime_windows()
    for seed in range(8):
        fit = wk.wk_means(wins, k=2, seed=seed)
        assert fit.dispersion[0] < fit.dispersion[1]
        assert fit.centroids[0].std() < fit.centroids[1].std()
        # The planted calm windows are the first 40 and must land in cluster 0.
        assert (fit.labels[:40] == 0).mean() > 0.9
        assert (fit.labels[40:] == 1).mean() > 0.9


def test_a_fit_returns_exactly_k_non_empty_clusters():
    fit = wk.wk_means(_two_regime_windows(), k=3, seed=0)
    assert fit.k == 3
    assert sorted(np.unique(fit.labels).tolist()) == [0, 1, 2]
    assert np.all(np.diff(fit.dispersion) >= 0)


def test_too_few_windows_is_refused_rather_than_fitted():
    with pytest.raises(wk.RegimeError, match="too few"):
        wk.wk_means(np.random.default_rng(0).normal(size=(5, 20)), k=2)


def test_k_beyond_the_data_is_refused():
    with pytest.raises(wk.RegimeError, match="k must be"):
        wk.wk_means(_two_regime_windows(), k=1)


# ── the score ─────────────────────────────────────────────────────────────


def test_mmd_is_near_zero_for_one_distribution_and_larger_for_two():
    rng = np.random.default_rng(0)
    a, b, far = rng.normal(0, 0.01, 300), rng.normal(0, 0.01, 300), rng.normal(0, 0.05, 300)
    s = mmd.median_sigma(a, b)
    assert mmd.mmd2(a, b, s) < mmd.mmd2(a, far, s)
    assert mmd.mmd2(a, a, s) == pytest.approx(0.0, abs=1e-12)


def test_mmd_is_never_negative():
    """The biased estimator is used so a score cannot read as -0.0003."""
    rng = np.random.default_rng(1)
    for _ in range(20):
        x, y = rng.normal(size=50), rng.normal(size=50)
        assert mmd.mmd2(x, y, mmd.median_sigma(x, y)) >= 0.0


def test_a_constant_series_does_not_divide_by_zero():
    flat = np.zeros(50)
    s = mmd.median_sigma(flat, flat)
    assert s > 0 and np.isfinite(mmd.mmd2(flat, flat, s))


def test_a_real_split_scores_above_one_and_a_meaningless_one_does_not():
    """The null the score exists to reject.

    Shuffling the labels of the same windows destroys the grouping and nothing
    else. A scoring scheme that cannot tell that apart from the real split is
    not evidence for anything, and this tab leads with the number.
    """
    wins = _two_regime_windows()
    real = np.array([0] * 40 + [1] * 20)
    noise = np.random.default_rng(0).permutation(real)

    assert mmd.score_labelling(wins, real, seed=0).ratio > 1.5
    assert mmd.score_labelling(wins, noise, seed=0).ratio < 1.2


def test_the_labellings_are_scored_on_identical_terms():
    """Same windows, same kernel width, same draws — or it is not a comparison."""
    p = syn.merton(seed=0)
    a = analyse(p.closes, _dates(p.closes.size), with_hmm=False)
    assert a.verdict.sigma == a.baseline_verdict.sigma
    assert a.verdict.draws == a.baseline_verdict.draws


# ── ground truth ──────────────────────────────────────────────────────────


def test_synthetic_paths_actually_contain_the_regimes_they_claim():
    """Guard the fixture itself — a generator that plants nothing tests nothing."""
    p = syn.merton(seed=3)
    assert 0.15 < p.stress_share < 0.45
    assert len(p.switches) == 6
    assert p.rets[p.stressed].std() > 1.5 * p.rets[~p.stressed].std()
    assert p.closes.size == p.rets.size + 1


def test_accuracy_scores_separate_the_never_fires_detector():
    """Their Defs. 3.7: a detector that never fires must score 0 on regime-on."""
    truth = np.array([False] * 80 + [True] * 20)
    silent = syn.score(np.zeros(100, dtype=bool), truth)
    assert silent.total == pytest.approx(0.8)
    assert silent.regime_off == pytest.approx(1.0)
    assert silent.regime_on == pytest.approx(0.0)


# ── the assembled analysis ────────────────────────────────────────────────


def test_analysis_labels_every_return_and_dates_the_episodes():
    p = syn.merton(seed=1)
    a = analyse(p.closes, _dates(p.closes.size), ticker="TEST", with_hmm=False)

    assert len(a.dates) == len(a.closes) == len(a.stress)
    assert a.episodes[0].start >= a.dates[0]
    assert a.episodes[-1].end <= a.dates[-1]
    assert sum(e.days for e in a.episodes) <= len(a.dates)
    assert all(e.name in detect.names_for(a.k) for e in a.episodes)


def test_centroid_quantiles_are_monotone_and_ordered_calm_first():
    a = analyse(syn.merton(seed=2).closes, _dates(2521), with_hmm=False)
    for c in a.centroids:
        q = np.array(c.quantiles, dtype=float)
        assert np.all(np.diff(q) >= -1e-12), f"{c.name} quantiles are not monotone"
    assert a.centroids[0].vol_pct < a.centroids[-1].vol_pct
    assert a.centroids[0].name == "calm"


def test_a_window_mean_is_a_day_not_an_annualised_quarter():
    """Scaling a 63-day mean by 252 prints "-117% a year" for an ordinary bad
    quarter. True arithmetic, useless statement, and it wrecked the scatter's
    axis. Windows report a day; only the centroids annualise."""
    a = analyse(syn.gbm(seed=5).closes, _dates(2521), with_hmm=False)
    assert max(abs(w.mean_day_pct) for w in a.windows) < 5.0


def test_dates_and_closes_must_line_up():
    with pytest.raises(wk.RegimeError, match="dates"):
        analyse(np.linspace(100, 120, 500), _dates(400))


def test_a_short_listing_is_refused_with_a_reason():
    with pytest.raises(wk.RegimeError, match="usable returns"):
        analyse(np.linspace(100, 120, 40), _dates(40))


# ── the route ─────────────────────────────────────────────────────────────


def test_route_returns_a_scored_labelling():
    r = client.get("/api/regimes/SPY", params={"days": 2520})
    if r.status_code in (404, 502):
        pytest.skip("no price data available offline")
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["ticker"] == "SPY"
    assert d["current"]["name"] in detect.names_for(d["params"]["k"])
    assert len(d["centroids"]) == d["params"]["k"]
    assert len(d["path"]["dates"]) == len(d["path"]["closes"]) == len(d["path"]["stress"])

    v = d["validation"]
    assert set(v) >= {"wasserstein", "volatility_ratio"}
    # One bandwidth across every labelling, or the numbers are not comparable
    # — and the tab draws them as bars on one axis.
    assert v["wasserstein"]["sigma"] == v["volatility_ratio"]["sigma"]
    assert d["caveats"], "the response must carry its own limitations"


def test_route_serves_the_fields_the_tab_draws():
    """The panel reads these by name; a rename here is a blank chart there."""
    r = client.get("/api/regimes/SPY", params={"days": 2520})
    if r.status_code in (404, 502):
        pytest.skip("no price data available offline")
    w = r.json()["windows_detail"][0]
    assert set(w) >= {"start", "end", "label", "mean_day_pct", "vol_pct", "kurtosis"}
    c = r.json()["centroids"][0]
    assert set(c) >= {"name", "share_pct", "vol_pct", "worst_day_pct", "quantiles"}


def test_route_rejects_an_overlap_that_swallows_the_window():
    assert client.get(
        "/api/regimes/SPY", params={"window_days": 30, "overlap_days": 30}
    ).status_code == 400


def test_route_rejects_a_bad_ticker_before_fetching():
    assert client.get("/api/regimes/../../etc/passwd").status_code in (400, 404)


# ── the plan metric ───────────────────────────────────────────────────────


class _Ctx:
    """The slice of the executor context this metric reads."""

    def __init__(self, closes, dates):
        import pandas as pd

        self._df = pd.DataFrame({"close": closes}, index=pd.to_datetime(dates))
        self.snapshot: dict = {}

    def price_frame(self, days: int):
        return self._df.iloc[-days:]


def test_metric_returns_exactly_what_it_declares():
    p = syn.merton(seed=4)
    m = get_metric("regime_clustering")
    got = m.fn(_Ctx(p.closes, _dates(p.closes.size)), **m.coerce_params({}))
    m.validate_output(got)  # raises on a missing or undeclared field

    assert got["regime"] in ("calm", "turbulent")
    assert got["calm_volatility_pct"] < got["turbulent_volatility_pct"]
    assert isinstance(got["separation_holds"], bool)
    assert got["windows"] > 0


def test_metric_reports_too_little_history_as_a_metric_error():
    m = get_metric("regime_clustering")
    with pytest.raises(MetricError):
        m.fn(_Ctx(np.linspace(100, 110, 60), _dates(60)), **m.coerce_params({}))


def test_metric_notes_warn_against_using_it_as_a_signal():
    """The lookahead caveat is load-bearing: it must reach the planner."""
    notes = get_metric("regime_clustering").notes.lower()
    assert "not what comes next" in notes or "not a signal" in notes
