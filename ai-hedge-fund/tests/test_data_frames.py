"""The price-frame shapes the providers actually return.

Each case here is a shape that one caller used to handle and another did not.
The point of the module is that every caller now gets the same answer, so the
cases are written against the shape rather than against a call site.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hedge_fund.data.frames import (
    close_series,
    dated_closes,
    latest_close,
    normalise_prices,
    simple_returns,
)

DAYS = pd.date_range("2024-01-01", periods=4, freq="D")


def test_lowercase_close_with_datetime_index() -> None:
    """The OpenBB shape, which five of the nine old call sites handled."""
    frame = normalise_prices(pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]}, index=DAYS))
    assert frame is not None
    assert list(frame["close"]) == [1.0, 2.0, 3.0, 4.0]
    assert isinstance(frame.index, pd.DatetimeIndex)


def test_capitalised_close() -> None:
    """The yfinance shape. Four old call sites read this as no price history."""
    frame = normalise_prices(pd.DataFrame({"Close": [1.0, 2.0]}, index=DAYS[:2]))
    assert frame is not None
    assert list(frame["close"]) == [1.0, 2.0]


def test_adjusted_close_only() -> None:
    """An adjusted feed names the column `Adj Close` and has no `close`."""
    frame = normalise_prices(pd.DataFrame({"Adj Close": [5.0, 6.0]}, index=DAYS[:2]))
    assert frame is not None
    assert list(frame["close"]) == [5.0, 6.0]


def test_close_wins_over_price() -> None:
    """Alias order decides, not column order."""
    frame = normalise_prices(
        pd.DataFrame({"price": [9.0, 9.0], "close": [1.0, 2.0]}, index=DAYS[:2])
    )
    assert frame is not None
    assert list(frame["close"]) == [1.0, 2.0]


def test_date_column_moves_to_the_index() -> None:
    """Some providers return the date as a column, not an index."""
    frame = normalise_prices(
        pd.DataFrame({"date": ["2024-01-02", "2024-01-01"], "close": [2.0, 1.0]})
    )
    assert frame is not None
    assert list(frame["close"]) == [1.0, 2.0], "rows must come back oldest first"
    assert "date" not in frame.columns


def test_list_of_records() -> None:
    """A cached payload arrives as a list of dicts, not a frame."""
    frame = normalise_prices(
        [{"date": "2024-01-01", "close": 1.0}, {"date": "2024-01-02", "close": 2.0}]
    )
    assert frame is not None
    assert list(frame["close"]) == [1.0, 2.0]


def test_newest_first_still_sorts() -> None:
    """latest_close must be the latest date, not the first row."""
    frame = pd.DataFrame({"close": [50.0, 10.0]}, index=DAYS[:2][::-1])
    assert latest_close(frame) == 50.0


def test_non_numeric_rows_are_dropped() -> None:
    frame = normalise_prices(pd.DataFrame({"close": ["1.5", "oops", "3.5"]}, index=DAYS[:3]))
    assert frame is not None
    assert list(frame["close"]) == [1.5, 3.5]


def test_tz_aware_index_floors_to_the_session() -> None:
    """A 09:30 New York stamp must become that calendar day, not the next."""
    idx = pd.DatetimeIndex(["2024-01-02 09:30", "2024-01-03 09:30"]).tz_localize("US/Eastern")
    frame = normalise_prices(pd.DataFrame({"close": [1.0, 2.0]}, index=idx), calendar_days=True)
    assert frame is not None
    assert frame.index.tz is None
    assert [str(d)[:10] for d in frame.index] == ["2024-01-02", "2024-01-03"]


def test_calendar_day_keeps_the_local_session() -> None:
    """A late close stays on its own trading day.

    Converting to UTC first pushes a 20:00 US/Eastern close onto the next
    calendar date and shifts a whole series by one bar.
    """
    frame = pd.DataFrame(
        {"close": [1.0]},
        index=pd.DatetimeIndex(["2024-03-15 20:00"]).tz_localize("US/Eastern"),
    )
    out = normalise_prices(frame, calendar_days=True)
    assert out is not None
    assert out.index[0] == pd.Timestamp("2024-03-15")


def test_two_tickers_join_after_calendar_days() -> None:
    """The reason `calendar_days` exists: a naive and an aware frame must join."""
    aware = pd.DataFrame(
        {"close": [1.0, 2.0]},
        index=pd.DatetimeIndex(["2024-01-02 09:30", "2024-01-03 09:30"]).tz_localize("US/Eastern"),
    )
    naive = pd.DataFrame(
        {"close": [3.0, 4.0]}, index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
    )
    left = close_series(aware, calendar_days=True)
    right = close_series(naive, calendar_days=True)
    assert left is not None and right is not None
    joined = pd.concat({"A": left, "B": right}, axis=1).dropna()
    assert len(joined) == 2


def test_zero_close_is_dropped_by_default() -> None:
    """A zero close turns one return into -100%."""
    close = close_series(pd.DataFrame({"close": [1.0, 0.0, 3.0, 4.0]}, index=DAYS))
    assert close is not None
    assert list(close) == [1.0, 3.0, 4.0]


def test_zero_close_is_kept_when_asked() -> None:
    close = close_series(pd.DataFrame({"close": [1.0, 0.0]}, index=DAYS[:2]), positive_only=False)
    assert close is not None
    assert list(close) == [1.0, 0.0]


def test_min_points_rejects_a_short_series() -> None:
    frame = pd.DataFrame({"close": [1.0, 2.0]}, index=DAYS[:2])
    assert close_series(frame, min_points=2) is not None
    assert close_series(frame, min_points=3) is None


def test_simple_returns_counts_closes_not_returns() -> None:
    rets = simple_returns(pd.DataFrame({"close": [100.0, 110.0, 121.0]}, index=DAYS[:3]))
    assert rets is not None
    assert len(rets) == 2
    assert rets.to_numpy() == pytest.approx([0.1, 0.1])
    assert np.isfinite(rets.to_numpy()).all()


def test_simple_returns_needs_three_closes() -> None:
    assert simple_returns(pd.DataFrame({"close": [100.0, 110.0]}, index=DAYS[:2])) is None


def test_dated_closes_are_parallel_lists() -> None:
    dates, closes = dated_closes(pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=DAYS[:3]))
    assert dates == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert closes == [1.0, 2.0, 3.0]
    assert len(dates) == len(closes)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        "not a frame",
        pd.DataFrame(),
        pd.DataFrame({"volume": [1, 2]}),
        pd.DataFrame({"close": ["a", "b"]}),
    ],
    ids=["none", "empty-list", "string", "empty-frame", "no-close", "all-unreadable"],
)
def test_unusable_input_returns_none_and_never_raises(raw: object) -> None:
    """Callers own the failure policy, so the module reports and does not raise."""
    assert normalise_prices(raw) is None
    assert close_series(raw) is None
    assert latest_close(raw) is None
    assert simple_returns(raw) is None
    assert dated_closes(raw) == ([], [])
