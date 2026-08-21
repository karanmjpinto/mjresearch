"""The autoresearch harness: splitting, units, overfit detection, the hurdle."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hedge_fund.autoresearch.harness import (
    MIN_OBSERVATIONS,
    OUT_OF_SAMPLE_FRACTION,
    HarnessError,
    describe_harness,
    evaluate,
    split_history,
    trials_adjusted_hurdle,
)


def _prices(n=600, drift=0.0004, vol=0.015, seed=0):
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000,
        },
        index=idx,
    )


# ----------------------------------------------------------------------
# Splitting
# ----------------------------------------------------------------------


def test_split_is_chronological_not_random():
    """A random split leaks the future backwards and invalidates the verdict."""
    ins, oos = split_history(_prices())
    assert ins.index.max() < oos.index.min()


def test_split_reserves_the_configured_fraction():
    ins, oos = split_history(_prices(1000))
    assert abs(len(oos) / 1000 - OUT_OF_SAMPLE_FRACTION) < 0.02


def test_short_history_is_refused_rather_than_split_thin():
    with pytest.raises(HarnessError, match="observations"):
        split_history(_prices(MIN_OBSERVATIONS - 10))


def test_empty_history_is_refused():
    with pytest.raises(HarnessError):
        split_history(pd.DataFrame())


# ----------------------------------------------------------------------
# Units — the engine reports fractions, these fields are percentages
# ----------------------------------------------------------------------


def test_percentage_fields_are_percentages():
    ev = evaluate(_prices(), "TEST", "buy_and_hold")
    in_market = ev.out_of_sample["time_in_market_pct"]
    assert in_market > 90, f"buy-and-hold should be ~100% invested, got {in_market}"


def test_buy_and_hold_is_not_warned_about_being_out_of_the_market():
    """It holds by definition; warning about it is noise, not insight."""
    ev = evaluate(_prices(), "TEST", "buy_and_hold")
    assert not any("barely in the market" in n for n in ev.notes)
    assert not any("out-of-sample trade" in n for n in ev.notes)


def test_a_rarely_trading_strategy_is_flagged():
    ev = evaluate(_prices(), "TEST", "golden_cross")
    if (ev.out_of_sample["trades"] or 0) < 3:
        assert any("close to noise" in n for n in ev.notes)


# ----------------------------------------------------------------------
# Evaluation contract
# ----------------------------------------------------------------------


def test_evaluation_reports_both_windows_and_a_baseline():
    ev = evaluate(_prices(), "TEST", "momentum")
    assert ev.in_sample["observations"] > 0
    assert ev.out_of_sample["observations"] > 0
    assert ev.baseline_out_of_sample is not None


def test_edge_is_measured_against_the_baseline_out_of_sample():
    ev = evaluate(_prices(), "TEST", "buy_and_hold")
    # Compared against itself, the edge is nil.
    assert ev.edge_vs_baseline == pytest.approx(0.0, abs=1e-6)


def test_unknown_strategy_is_refused():
    with pytest.raises(HarnessError, match="unknown strategy"):
        evaluate(_prices(), "TEST", "invented_strategy")


def test_evaluation_is_deterministic():
    df = _prices()
    assert (
        evaluate(df, "TEST", "rsi_reversion").as_dict()
        == evaluate(df, "TEST", "rsi_reversion").as_dict()
    )


def test_degradation_is_in_sample_minus_out_of_sample():
    ev = evaluate(_prices(), "TEST", "momentum")
    expected = ev.in_sample["sharpe_ratio"] - ev.out_of_sample["sharpe_ratio"]
    assert ev.degradation == pytest.approx(expected, abs=1e-3)


# ----------------------------------------------------------------------
# The multiple-testing hurdle
# ----------------------------------------------------------------------


def test_hurdle_is_the_baseline_for_a_single_trial():
    assert trials_adjusted_hurdle(1, 500, base_sharpe=0.4) == pytest.approx(0.4)


def test_hurdle_rises_with_the_number_of_trials():
    """Search maximises noise. The hundredth idea must clear a higher bar."""
    h10 = trials_adjusted_hurdle(10, 500)
    h100 = trials_adjusted_hurdle(100, 500)
    h500 = trials_adjusted_hurdle(500, 500)
    assert h10 < h100 < h500


def test_hurdle_falls_with_more_evidence():
    """A longer out-of-sample window makes the estimate less noisy."""
    assert trials_adjusted_hurdle(50, 2000) < trials_adjusted_hurdle(50, 250)


def test_hurdle_is_measured_from_the_baseline():
    assert trials_adjusted_hurdle(50, 500, base_sharpe=1.0) > trials_adjusted_hurdle(50, 500, 0.0)


def test_hurdle_tolerates_degenerate_input():
    assert trials_adjusted_hurdle(0, 0) is not None


# ----------------------------------------------------------------------
# Self-description
# ----------------------------------------------------------------------


def test_harness_describes_its_own_rules():
    d = describe_harness()
    assert d["verdict_window"] == "out_of_sample"
    assert d["primary_metric"] == "sharpe_ratio"
    assert d["baseline_strategy"] in d["strategies"]
