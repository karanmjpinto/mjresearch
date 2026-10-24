"""The split-halves verdict: a whole-window win must also hold in each half."""

import pandas as pd

from hedge_fund.quant.backtest.engine import split_verdict


def _series(rets: list[float]) -> tuple[pd.Series, pd.Series]:
    idx = pd.date_range("2020-01-01", periods=len(rets), freq="B")
    r = pd.Series(rets, index=idx)
    return (1 + r).cumprod(), r


def _verdict(strat: list[float], bench: list[float]) -> dict:
    eq, r = _series(strat)
    bm, br = _series(bench)
    return split_verdict(eq, r, pd.Series(1.0, index=r.index), bm, br, rf_annual=0.0)


def test_win_in_both_halves_holds():
    # Strategy: steady gains with mild noise; benchmark: flat and noisier.
    strat = [0.002, 0.001] * 100
    bench = [0.004, -0.004] * 100
    v = _verdict(strat, bench)
    assert v["label"] == "holds"
    assert len(v["halves"]) == 2


def test_win_only_in_first_half_is_no_edge():
    # Same overall shape as a winner, but the second half loses on both measures.
    strat = [0.002, 0.001] * 50 + [-0.002, -0.001] * 50
    bench = [0.0005, 0.0] * 100
    v = _verdict(strat, bench)
    assert v["label"] == "no_edge"
    assert not v["cagr_holds"] and not v["sharpe_holds"]
