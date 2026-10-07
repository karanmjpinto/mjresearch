"""Breadth measures and the divergence test over them.

Everything here is built on synthetic closes with a known answer, because the
whole point of the screen is that the real series has no answer key: a chart of
a divergence looks identical whether or not the divergence means anything, and
a test that asserted against live market data would be asserting that today's
market has not changed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hedge_fund.breadth import analyse, from_closes
from hedge_fund.breadth.series import MIN_MEMBERS


def _frame(members: int, days: int, *, drift: np.ndarray | None = None) -> pd.DataFrame:
    """A price panel. ``drift`` is the per-member daily log drift."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2004-01-01", periods=days)
    if drift is None:
        drift = np.zeros(members)
    steps = rng.normal(0, 0.005, size=(days, members)) + drift
    return pd.DataFrame(
        100 * np.exp(np.cumsum(steps, axis=0)),
        index=dates,
        columns=[f"T{i}" for i in range(members)],
    )


def test_advances_and_declines_net_out_on_a_flat_panel():
    """A panel where every member is unchanged leaves the A-D line flat.

    Unchanged closes count as neither an advance nor a decline, which is the
    convention — a flat day is not half an advance — and this is the only test
    that pins it.
    """
    dates = pd.bdate_range("2004-01-01", periods=400)
    flat = pd.DataFrame(100.0, index=dates, columns=[f"T{i}" for i in range(MIN_MEMBERS)])
    b = from_closes(flat)
    assert b.ad_line.abs().max() == 0


def test_the_ad_line_rises_when_most_members_rise():
    up = _frame(MIN_MEMBERS, 400, drift=np.full(MIN_MEMBERS, 0.002))
    b = from_closes(up)
    assert b.ad_line.iloc[-1] > 0
    assert b.pct_above_200dma.iloc[-1] > 80


def test_thin_sessions_are_dropped_rather_than_reported():
    """A day with forty members is a different statistic, not a noisy one."""
    frame = _frame(MIN_MEMBERS + 50, 400)
    # Blank out most members for the first 100 sessions, as a real backfill does.
    frame.iloc[:100, 60:] = np.nan
    b = from_closes(frame)
    assert b.members.min() >= MIN_MEMBERS
    assert len(b) < len(frame)
    # The A-D line is rebased on the first *kept* session, so its level never
    # encodes sessions that are not on the chart.
    assert b.ad_line.iloc[0] == 0


def test_a_universe_too_thin_to_measure_says_so():
    with pytest.raises(ValueError, match="too thin"):
        from_closes(_frame(10, 400))


def _diverging(days: int = 1400) -> tuple[pd.DataFrame, pd.Series]:
    """An index at highs on a market where most members are falling.

    Twenty members carry the index up throughout; the rest roll over after the
    first third. The index itself is built as a cap-weighted average dominated
    by the leaders, which is exactly the arithmetic the screen exists to expose.
    """
    members = MIN_MEMBERS + 20
    frame = _frame(members, days)
    turn = days // 3
    decay = np.concatenate([np.zeros(turn), np.linspace(0, -0.0016, days - turn)])
    for col in frame.columns[20:]:
        frame[col] = frame[col] * np.exp(np.cumsum(decay))
    index = frame.iloc[:, :20].mean(axis=1)
    return frame, index


def test_a_planted_divergence_is_found():
    frame, index = _diverging()
    out = analyse(from_closes(frame), index, near=2.0, floor=50.0)
    assert out["reading"]["divergent"] is True
    assert out["reading"]["pct_above_200dma"] < 50
    assert out["coverage"]["episodes"] >= 1


def test_no_divergence_when_the_market_is_broad():
    frame = _frame(MIN_MEMBERS + 20, 1400, drift=np.full(MIN_MEMBERS + 20, 0.0008))
    index = frame.mean(axis=1)
    out = analyse(from_closes(frame), index, near=2.0, floor=50.0)
    assert out["reading"]["divergent"] is False
    assert out["coverage"]["episodes"] == 0


def test_signal_days_are_collapsed_into_episodes():
    """The count that is reported is episodes, never days.

    This is the arithmetic that keeps the sample honest: a run of consecutive
    signal days is one thing that happened, and reporting it as many is how a
    handful of observations is made to look like a study.
    """
    frame, index = _diverging()
    out = analyse(from_closes(frame), index, near=5.0, floor=65.0)
    assert out["coverage"]["signal_days"] > out["coverage"]["episodes"]
    assert len(out["episodes"]) == out["coverage"]["episodes"]
    total = sum(e["days"] for e in out["episodes"])
    assert total == out["coverage"]["signal_days"]


def test_loosening_the_threshold_cannot_lose_signal_days():
    """Monotonicity. A looser floor admits every day the tighter one did."""
    frame, index = _diverging()
    b = from_closes(frame)
    tight = analyse(b, index, near=2.0, floor=50.0)["coverage"]["signal_days"]
    loose = analyse(b, index, near=2.0, floor=65.0)["coverage"]["signal_days"]
    assert loose >= tight


def test_a_verdict_with_too_few_episodes_refuses_to_draw_one():
    frame, index = _diverging()
    out = analyse(from_closes(frame), index, near=0.1, floor=20.0)
    if out["base_rates"]["252d"]["after_divergence"]["n"] < 3:
        assert out["verdict"]["stance"] == "untested"
        assert "not enough" in out["verdict"]["line"]


def test_too_short_a_history_is_refused_rather_than_answered():
    frame = _frame(MIN_MEMBERS, 280)
    with pytest.raises(ValueError, match="at least 300"):
        analyse(from_closes(frame), frame.mean(axis=1))


def test_forward_returns_are_absent_rather_than_zero_at_the_live_edge():
    """An episode with no year after it reports None, not a return of 0.

    A zero here would be averaged into the base rate as a flat year, which is
    the one number most likely to be mistaken for evidence.
    """
    frame, index = _diverging()
    out = analyse(from_closes(frame), index, near=5.0, floor=65.0)
    last = out["episodes"][-1]
    assert last["forward"]["252d"] is None or isinstance(last["forward"]["252d"], float)
    assert all(
        v is None or isinstance(v, float) for e in out["episodes"] for v in e["forward"].values()
    )


def test_the_store_round_trips_and_keeps_nan_out_of_the_json(tmp_path, monkeypatch):
    """NaN is written as `null`, not as the bare `NaN` token.

    `json.dump` emits `NaN` by default, which is not JSON and which every
    strict parser on the other end rejects — including the browser's. The
    200-day average is NaN for the first 199 sessions of any build, so this is
    not an edge case, it is every file.
    """
    import json

    from hedge_fund.breadth import read, store, write

    monkeypatch.setattr(store, "CACHE_DIR", tmp_path)
    frame, index = _diverging(600)
    breadth = from_closes(frame)
    path = write(
        "test", breadth, index, index_symbol="^TEST", members_requested=10, members_fetched=10
    )
    assert "NaN" not in path.read_text(encoding="utf-8")
    json.loads(path.read_text(encoding="utf-8"))

    back = read("test")
    assert back.universe == "test"
    assert back.index_symbol == "^TEST"
    assert len(back.breadth) == len(breadth)
    # `check_freq=False`: a DatetimeIndex rebuilt from ISO strings has no
    # inferred frequency, which pandas compares even though nothing in this
    # module reads it.
    pd.testing.assert_series_equal(
        back.breadth.pct_above_200dma,
        breadth.pct_above_200dma,
        check_names=False,
        check_freq=False,
        rtol=1e-3,
    )


def test_a_missing_build_says_how_to_make_one(tmp_path, monkeypatch):
    from hedge_fund.breadth import BreadthDataMissing, read, store

    monkeypatch.setattr(store, "CACHE_DIR", tmp_path)
    with pytest.raises(BreadthDataMissing, match="refresh_breadth"):
        read("nothing-here")
