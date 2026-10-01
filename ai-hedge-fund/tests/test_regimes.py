"""Regime detection: the clustering, the hidden chain, and what each is for.

Two different things are being guarded here.

The Wasserstein side is guarded against silent degradation. There is no answer
key on real prices, so the accuracy floors are asserted on
:mod:`hedge_fund.regimes.synthetic` paths whose regimes were planted — the only
place an accuracy figure can honestly exist.

The HMM side is guarded against the opposite failure: being believed. It is
the better detector on Gaussian paths and a much worse one the moment returns
jump, and both halves of that are asserted, because the temptation with a
model this well known is to quietly promote it on the strength of its
reputation. Its arithmetic is pinned separately against the worked example in
Jurafsky and Martin's Appendix A, where every intermediate value is printed.
"""

from __future__ import annotations

import numpy as np
import pytest

from hedge_fund.regimes import detect, hmm, mmd, synthetic
from hedge_fund.regimes import wasserstein as wk
from hedge_fund.regimes.wasserstein import RegimeError


def _dates(n: int) -> list[str]:
    start = np.datetime64("2014-01-02")
    return [str(start + np.timedelta64(i, "D")) for i in range(n)]


# ── The textbook model (Jurafsky & Martin, Fig. A.2) ──────────────────────
#
# States ordered (COLD, HOT) so index 1 is the hot state, matching the figure's
# q2. pi = [.2, .8]; the ice-cream counts 1, 2, 3 index the emission columns.

ICE_A = np.array([[0.5, 0.5], [0.4, 0.6]])
ICE_PI = np.array([0.2, 0.8])
ICE_B = np.array([[0.5, 0.4, 0.1], [0.2, 0.4, 0.4]])


def _ice(obs: list[int]) -> np.ndarray:
    return np.array([ICE_B[:, o - 1] for o in obs], dtype=np.float64)


def test_forward_reproduces_the_printed_trellis():
    """Their Fig. A.5, cell by cell, for the observations 3 1 3."""
    fwd = hmm.forward(_ice([3, 1, 3]), ICE_A, ICE_PI)
    raw = hmm.unscale(fwd.alpha, fwd.scale)

    assert raw[0] == pytest.approx([0.02, 0.32])  # alpha_1(C), alpha_1(H)
    assert raw[1] == pytest.approx([0.069, 0.0404])  # alpha_2(C), alpha_2(H)
    # Termination, their eq. A.10: P(O|lambda) is the sum of the last column.
    assert np.exp(fwd.loglik) == pytest.approx(float(raw[2].sum()))


def test_scaling_is_the_only_difference_from_the_chapters_pseudocode():
    """Each scaled column is a posterior, and the normalisers carry the mass."""
    fwd = hmm.forward(_ice([3, 1, 3]), ICE_A, ICE_PI)
    assert fwd.alpha.sum(axis=1) == pytest.approx([1.0, 1.0, 1.0])
    assert float(-np.log(fwd.scale).sum()) == pytest.approx(fwd.loglik)


def test_viterbi_finds_the_path_the_figure_computes():
    """Their Fig. A.8 — and not the sequence their prose names.

    The chapter's text says the decoder should return H H H, but its own
    trellis puts v_2(C) = .064 above v_2(H) = .038, and extending both gives
    P(H C H) = .0128 against P(H H H) = .0092. The figure is right; this test
    follows the arithmetic rather than the sentence, so that a future change to
    the recursion cannot hide behind the discrepancy.
    """
    path, logp = hmm.viterbi(_ice([3, 1, 3]), ICE_A, ICE_PI)
    assert list(path) == [1, 0, 1]  # H C H
    assert np.exp(logp) == pytest.approx(0.0128)
    hhh = 0.8 * 0.4 * 0.6 * 0.2 * 0.6 * 0.4
    assert np.exp(logp) > hhh


def test_forward_and_backward_agree_on_the_likelihood():
    """Their eq. A.21: alpha_t . beta_t is the same total at every t."""
    b = _ice([3, 1, 3, 2, 1])
    fwd = hmm.forward(b, ICE_A, ICE_PI)
    beta = hmm.backward(b, ICE_A, fwd.scale)
    unscaled = hmm.unscale(fwd.alpha, fwd.scale) * (beta / np.cumprod(fwd.scale[::-1])[::-1, None])
    assert unscaled.sum(axis=1) == pytest.approx([np.exp(fwd.loglik)] * b.shape[0])


def test_estep_counts_are_probabilities():
    e = hmm.estep(_ice([3, 1, 3, 2, 1]), ICE_A, ICE_PI)
    assert e.gamma.sum(axis=1) == pytest.approx(np.ones(5))
    # xi is summed over the T-1 transitions, so that is its total mass.
    assert float(e.xi.sum()) == pytest.approx(4.0)


def test_baum_welch_climbs_the_likelihood_it_is_given():
    """EM's one guarantee, asserted on every iteration rather than assumed."""
    rng = np.random.default_rng(7)
    rets = np.concatenate([rng.normal(0, 0.007, 400), rng.normal(0, 0.03, 200)])

    pi, a, means, sigmas = hmm._seed_params(rets, 2, rng, jitter=False)
    last = -np.inf
    for _ in range(12):
        b, shift = hmm.emissions(rets, means, sigmas)
        e = hmm.estep(b, a, pi, shift)
        assert e.loglik >= last - 1e-8, "Baum-Welch went downhill"
        last = e.loglik
        pi, a, means, sigmas = hmm._mstep(rets, e)


# ── The fitted model ──────────────────────────────────────────────────────


def test_states_come_back_calm_first_with_a_stochastic_matrix():
    path = synthetic.gbm(1500, seed=1)
    fit = hmm.fit(path.rets, 2, seed=0)

    assert fit.sigmas[0] < fit.sigmas[1], "state 0 must be the calm one"
    assert fit.transition.sum(axis=1) == pytest.approx([1.0, 1.0])
    assert fit.start.sum() == pytest.approx(1.0)
    assert fit.next_day.sum() == pytest.approx(1.0)
    assert (fit.transition > 0).all(), "a zeroed transition can never recover"


def test_expected_duration_is_the_transition_diagonal_not_a_measurement():
    fit = hmm.fit(synthetic.gbm(2520, seed=0).rets, 2, seed=0)
    assert fit.expected_days == pytest.approx(1.0 / (1.0 - fit.persistence))


def test_a_fit_is_deterministic_given_a_seed():
    rets = synthetic.merton(1500, seed=4).rets
    first, second = hmm.fit(rets, 2, seed=3), hmm.fit(rets, 2, seed=3)
    assert first.loglik == pytest.approx(second.loglik)
    assert list(first.path) == list(second.path)


def test_a_series_too_short_or_too_flat_is_refused_not_guessed():
    with pytest.raises(RegimeError):
        hmm.fit(np.zeros(20), 2)
    with pytest.raises(RegimeError):
        hmm.fit(np.full(500, 0.001), 2)


def test_a_state_cannot_collapse_onto_one_observation():
    """The Gaussian degeneracy: sigma -> 0 sends the likelihood to infinity."""
    rng = np.random.default_rng(0)
    rets = np.concatenate([rng.normal(0, 0.01, 600), [0.4]])  # one huge outlier
    fit = hmm.fit(rets, 2, seed=0)
    assert np.isfinite(fit.loglik)
    assert (fit.sigmas >= hmm.MIN_SIGMA).all()


# ── What each method is actually good at ──────────────────────────────────
#
# The paper (Horvath, Issa, Muguruza) and the chapter disagree about which
# model to reach for, and both are right about different data. These two tests
# are the reason both are in the package, and the reason neither is presented
# as the upgrade.


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_on_gaussian_paths_the_chain_is_the_better_detector(seed: int):
    """gBm is the HMM's own generative model, so it should win here."""
    path = synthetic.gbm(2520, seed=seed)
    chain = synthetic.score(hmm.fit(path.rets, 2, seed=0).path == 1, path.stressed)
    assert chain.regime_on > 0.90
    assert chain.total > 0.95


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_when_returns_jump_the_chain_models_the_jumps_not_the_regime(seed: int):
    """The failure the package is built around, pinned so it cannot be forgotten.

    Under Merton jumps the second state stops being a regime and becomes a
    one- or two-day outlier bucket: a Gaussian emission cannot produce a jump,
    so maximum likelihood buys one cheaply with a wide, short-lived state. The
    clustering, which never assumes a shape for the returns, keeps working.

    This is the same ordering the paper reports (their Table 4) and the same
    one ``synthetic.Accuracy`` describes.
    """
    path = synthetic.merton(2520, seed=seed)
    fit = hmm.fit(path.rets, 2, seed=0)
    chain = synthetic.score(fit.path == 1, path.stressed)

    wins = wk.windows(path.rets, 63, 42)
    spans = wk.window_spans(wins.shape[0], 63, 42)
    labels = wk.wk_means(wins, 2, seed=0).labels
    cluster = synthetic.score(
        detect._per_return_label(labels, spans, path.rets.size, 2) >= 1, path.stressed
    )

    assert cluster.regime_on > 0.80, "the clustering must survive jumps"
    assert chain.regime_on < 0.60, "if the chain starts finding jump regimes, re-read this test"
    assert cluster.regime_on > chain.regime_on + 0.30
    assert fit.expected_days[1] < 10, "the turbulent state is a jump bucket, not a stretch"


@pytest.mark.parametrize("seed", [0, 1])
def test_the_clustering_beats_the_volatility_rule_it_replaced(seed: int):
    path = synthetic.merton(2520, seed=seed)
    wins = wk.windows(path.rets, 63, 42)
    spans = wk.window_spans(wins.shape[0], 63, 42)

    cluster = synthetic.score(
        detect._per_return_label(wk.wk_means(wins, 2, seed=0).labels, spans, path.rets.size, 2)
        >= 1,
        path.stressed,
    )
    ratio = synthetic.score(
        detect._per_return_label(detect.ratio_labels(wins, path.rets), spans, path.rets.size, 2)
        >= 1,
        path.stressed,
    )
    assert cluster.regime_on > ratio.regime_on


# ── The assembled analysis ────────────────────────────────────────────────


def test_analyse_reports_all_three_labellings_on_one_scale():
    path = synthetic.merton(2000, seed=0)
    out = detect.analyse(path.closes, _dates(path.closes.size), ticker="TEST", seed=0)
    payload = out.as_dict()

    scored = payload["validation"]
    assert set(scored) >= {"wasserstein", "volatility_ratio", "hmm"}
    # The comparison is only meaningful if the kernel is shared.
    assert scored["volatility_ratio"]["sigma"] == scored["wasserstein"]["sigma"]
    assert scored["hmm"]["sigma"] == scored["wasserstein"]["sigma"]
    assert scored["hmm"]["draws"] == scored["wasserstein"]["draws"] == mmd.DRAWS
    assert out.verdict.holds, "WK-means should separate a jump-switched path"


def test_the_analysis_carries_the_transition_matrix_the_clustering_cannot():
    out = detect.analyse(synthetic.gbm(2000, seed=2).closes, _dates(2001), ticker="TEST", seed=0)
    chain = out.hmm
    assert chain is not None

    rows = chain.transition
    assert [sum(r) for r in rows] == pytest.approx([1.0] * len(rows))
    assert sum(s.next_day_pct for s in chain.states) == pytest.approx(100.0)
    assert chain.current in chain.states
    assert all(s.expected_days > 0 for s in chain.states)
    assert 0.0 <= chain.current_posterior_pct <= 100.0
    # The posterior is one number per return, and it is a probability.
    assert len(chain.posterior) == out.observations - 1
    assert all(0.0 <= v <= 1.0 for v in chain.posterior)


def test_the_hmm_can_be_skipped_and_the_rest_still_stands():
    closes = synthetic.gbm(1200, seed=0).closes
    out = detect.analyse(closes, _dates(closes.size), seed=0, with_hmm=False)
    assert out.hmm is None
    assert out.as_dict()["hmm"] is None
    assert out.as_dict()["validation"]["hmm"] is None
    assert out.verdict.ratio > 0


def test_the_decoded_state_and_the_final_posterior_are_both_reported():
    """They can disagree at the end of a series, and a reader must see both.

    The backward pass starts from beta_T = 1, so the last days have no future
    evidence anchoring them and their marginals drift; the Viterbi path does
    not, because the transition penalty still applies. Collapsing the two into
    one number would present the least reliable part of the fit as settled.
    """
    out = detect.analyse(synthetic.gbm(2520, seed=5).closes, _dates(2521), ticker="TEST", seed=0)
    chain = out.hmm
    assert chain is not None
    payload = chain.as_dict()["current"]
    assert payload["posterior_pct"] is not None
    assert payload["name"] == chain.current.name
    # The per-return posterior ends where the current-day figure says it does.
    stressed_today = chain.posterior[-1] * 100.0
    expected = stressed_today if chain.current.label >= 1 else 100.0 - stressed_today
    assert chain.current_posterior_pct == pytest.approx(expected, abs=0.5)


def test_the_caveats_say_the_transition_matrix_is_not_a_forecast():
    """A number that looks like a prediction must arrive with its limits."""
    joined = " ".join(detect.CAVEATS).lower()
    assert "forecast" in joined
    assert "jump" in joined
