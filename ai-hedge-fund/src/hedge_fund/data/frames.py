"""One answer to "what is the close price?" for every caller in the app.

Providers disagree about the shape of a price frame. yfinance capitalises its
columns and indexes on a `DatetimeIndex`; OpenBB lower-cases them and sometimes
hands back a `date` column instead; a cached payload arrives as a list of
dicts; an adjusted feed names the column `Adj Close` and no `close` exists at
all. Several also carry a tz-aware index, or a 09:30 session time rather than
midnight.

Nine call sites used to each answer that on their own, and they did not agree.
Five accepted only a column literally named `close`, so a provider that
returned `Adj Close` silently produced "no price history" in the regimes tab
while the backtest engine on the same ticker worked. Three normalised the
index, six did not. Two dropped non-positive prices, seven kept them, and a
zero close turns one return into -100%.

This module owns that mechanic, so a fix lands once. It owns no policy: every
function reports failure as `None` or an empty result, and the caller decides
whether that is a 404, a 502, a `MetricError`, or a skipped ticker.

Reach for:

    normalise_prices   the whole frame, dated and numeric — for anything that
                       needs volume, highs, or the index
    close_series       just the close column, indexed by date
    latest_close       one float, the spot price
    simple_returns     period-over-period returns
    dated_closes       parallel date and close lists, for JSON responses
    price_summary      the current/change/high/low panel, as a dict
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

#: Column names that mean "the close price", in the order we prefer them.
#: Compared after lower-casing and stripping, so `Adj Close` matches
#: `adj close`. `price` is last because a frame that has both a close and a
#: generic price column means the close.
CLOSE_ALIASES: tuple[str, ...] = (
    "close",
    "adjclose",
    "adj close",
    "adjusted_close",
    "adjusted close",
    "price",
)

#: Column names that mean "the date of this row".
DATE_ALIASES: tuple[str, ...] = ("date", "datetime", "timestamp", "index")

__all__ = [
    "CLOSE_ALIASES",
    "DATE_ALIASES",
    "close_series",
    "dated_closes",
    "latest_close",
    "normalise_prices",
    "price_summary",
    "simple_returns",
]


def _as_frame(raw: Any) -> pd.DataFrame | None:
    """A DataFrame out of a frame, a list of records, a wrapper, or nothing.

    Three shapes arrive from the provider chain: a DataFrame, a list of record
    dicts from a cache, and a `{"data": [...]}` envelope from the JSON paths.
    """
    if raw is None:
        return None
    if isinstance(raw, pd.DataFrame):
        frame = raw.copy()
    elif isinstance(raw, list):
        if not raw:
            return None
        frame = pd.DataFrame(raw)
    elif isinstance(raw, dict) and isinstance(raw.get("data"), list):
        if not raw["data"]:
            return None
        frame = pd.DataFrame(raw["data"])
    else:
        return None
    return None if frame.empty else frame


def _find(columns: Any, aliases: tuple[str, ...]) -> Any:
    """The first column whose lower-cased name is in `aliases`.

    Alias order wins over column order: a frame with both `price` and `close`
    must resolve to `close`, whichever came first in the frame.
    """
    lowered: dict[str, Any] = {}
    for col in columns:
        key = str(col).strip().lower()
        lowered.setdefault(key, col)
    for alias in aliases:
        if alias in lowered:
            return lowered[alias]
    return None


def _calendar_days(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Floor an index to the local calendar day and drop the zone.

    Two series stamped 09:30 and 00:00 on the same session join to an empty
    frame, and a tz-aware series concatenated with a naive one raises outright.
    Both read to a caller as "these tickers never traded together".

    Local day, not UTC: an index already in US/Eastern must keep the session it
    belongs to, and converting to UTC first moves a 20:00 close onto the next
    date.
    """
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def normalise_prices(
    raw: Any,
    *,
    calendar_days: bool = False,
) -> pd.DataFrame | None:
    """A price frame with lower-cased columns, a `close`, and a date index.

    Does five things, in order: lower-cases the column names, renames whichever
    close alias is present to `close`, moves a date column into the index,
    sorts chronologically, and coerces `close` to a number. Rows with an
    unreadable close are dropped.

    Set `calendar_days` to floor the index to the day and drop the time zone.
    Do that when the frame will be joined to another ticker's frame; leave it
    off when the caller needs intraday stamps.

    Returns None when the input is empty, is not a frame or list of records, or
    carries no recognisable close column. A frame comes back only when it has
    at least one usable row.
    """
    frame = _as_frame(raw)
    if frame is None:
        return None

    frame.columns = [str(c).strip().lower() for c in frame.columns]

    close_col = _find(frame.columns, CLOSE_ALIASES)
    if close_col is None:
        return None
    if close_col != "close":
        # Drop an existing unusable `close` first, or the rename collides and
        # pandas keeps two columns of the same name.
        if "close" in frame.columns:
            frame = frame.drop(columns=["close"])
        frame = frame.rename(columns={close_col: "close"})

    date_col = _find([c for c in frame.columns if c != "close"], DATE_ALIASES)
    if date_col is not None:
        stamps = pd.to_datetime(frame[date_col], errors="coerce", utc=False)
        frame = frame.loc[stamps.notna()]
        frame = frame.set_index(pd.DatetimeIndex(stamps.dropna())).drop(columns=[date_col])
    elif not isinstance(frame.index, pd.DatetimeIndex):
        stamps = pd.to_datetime(frame.index, errors="coerce")
        frame = frame.loc[stamps.notna()]
        frame.index = pd.DatetimeIndex(stamps.dropna())

    if calendar_days and isinstance(frame.index, pd.DatetimeIndex):
        frame.index = _calendar_days(frame.index)

    frame = frame.sort_index()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["close"])
    return None if frame.empty else frame


def close_series(
    raw: Any,
    *,
    positive_only: bool = True,
    min_points: int = 1,
    calendar_days: bool = False,
) -> pd.Series | None:
    """The close column alone, numeric and date-indexed.

    `positive_only` drops prices at or below zero. Keep it on for anything that
    takes a ratio or a return: a zero close makes one period read as -100%.
    Turn it off only to report a raw provider value.

    `min_points` is the shortest series the caller can use. Returns None when
    the frame is unusable or the series is shorter than that.
    """
    frame = normalise_prices(raw, calendar_days=calendar_days)
    if frame is None:
        return None
    close = frame["close"]
    if positive_only:
        close = close[close > 0]
    return None if len(close) < max(min_points, 1) else close


def latest_close(raw: Any, *, positive_only: bool = True) -> float | None:
    """The most recent close, or None.

    The spot price. Sorts the frame first, so a provider that returns newest
    first does not give the oldest price.
    """
    close = close_series(raw, positive_only=positive_only)
    return None if close is None else float(close.iloc[-1])


def simple_returns(raw: Any, *, min_points: int = 3) -> pd.Series | None:
    """Period-over-period returns, with the non-finite values removed.

    `min_points` counts closes, not returns, because a caller thinks in bars.
    Three closes give two returns, which is the least that can show dispersion.
    """
    close = close_series(raw, min_points=min_points)
    if close is None:
        return None
    rets = close.pct_change().dropna()
    if rets.empty:
        return None
    rets = rets[np.isfinite(rets.to_numpy())]
    return None if rets.empty else rets


def dated_closes(raw: Any) -> tuple[list[str], list[float]]:
    """Parallel `YYYY-MM-DD` dates and closes, for a JSON response.

    Returns two empty lists when the frame is unusable. The lists are always
    the same length.
    """
    close = close_series(raw)
    if close is None:
        return [], []
    return (
        [str(d)[:10] for d in close.index],
        [float(v) for v in close.to_numpy()],
    )


def price_summary(raw: Any) -> dict[str, float]:
    """The four numbers every price panel in the app shows.

    `current`, `change_pct` over the whole window, and the window `high` and
    `low`. An empty dict means there was no usable history, which every caller
    already renders as "no price data" — so this never raises on a bad frame.

    The `*_30d` key names are kept because the frontend and the API contract
    use them. They are not thirty days: the window is whatever the caller
    fetched, and renaming them is a separate, breaking change.
    """
    close = close_series(raw, min_points=1)
    if close is None:
        return {}
    first = float(close.iloc[0])
    last = float(close.iloc[-1])
    return {
        "current": last,
        "change_30d_pct": round((last / first - 1) * 100, 2) if first else 0.0,
        "high_30d": float(close.max()),
        "low_30d": float(close.min()),
    }
