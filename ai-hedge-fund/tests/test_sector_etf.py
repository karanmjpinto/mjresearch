"""Sector drift computed from ETF closes.

The behaviour worth protecting is the period arithmetic, because it is the part
a reader cannot check: a window measured from the wrong close still produces a
plausible percentage. Every test here supplies its own price frame, so none of
them reach the network and the expected answers are arithmetic rather than
whatever the market did today.
"""

from __future__ import annotations

import pandas as pd
import pytest

from hedge_fund.data.cache import DataCategory
from hedge_fund.data.providers.sector_etf_provider import (
    SECTOR_ETFS,
    SectorETFProvider,
    _change_since,
    _rank,
    _session_change,
)


def _frame(series: dict[str, list[float]], *, end: str = "2026-09-11") -> pd.DataFrame:
    """Business-day closes ending on `end`, one column per ticker."""
    length = max(len(v) for v in series.values())
    idx = pd.bdate_range(end=end, periods=length)
    return pd.DataFrame(
        {t: pd.Series(v, index=idx[len(idx) - len(v) :]) for t, v in series.items()}
    )


def _provider(frame: pd.DataFrame) -> SectorETFProvider:
    p = SectorETFProvider()
    p._download_closes = lambda tickers, days: frame  # type: ignore[method-assign]
    return p


# --- the provider contract ---------------------------------------------------


def test_it_needs_no_api_key() -> None:
    """The whole point of deriving this: nothing to configure, nothing to expire."""
    assert SectorETFProvider().available() is True


def test_it_only_answers_for_sector_performance() -> None:
    p = _provider(_frame({"XLK": [100.0, 101.0]}))
    assert p.fetch(DataCategory.PRICE, "AAPL") is None


def test_every_gics_sector_has_exactly_one_fund() -> None:
    assert len(SECTOR_ETFS) == 11
    assert len(set(SECTOR_ETFS.values())) == 11, "two funds claiming one sector"


# --- period arithmetic -------------------------------------------------------


def test_one_day_is_the_previous_close_not_the_first_one() -> None:
    s = pd.Series([50.0, 100.0, 110.0], index=pd.bdate_range(end="2026-09-11", periods=3))
    assert _session_change(s, 1) == 10.0


def test_five_day_counts_sessions_so_a_holiday_cannot_shorten_it() -> None:
    """Six closes, so five sessions back is the first of them."""
    s = pd.Series([100.0, 1, 2, 3, 4, 120.0], index=pd.bdate_range(end="2026-09-11", periods=6))
    assert _session_change(s, 5) == 20.0


def test_a_window_longer_than_the_history_is_unanswered_not_zero() -> None:
    s = pd.Series([100.0, 110.0], index=pd.bdate_range(end="2026-09-11", periods=2))
    assert _session_change(s, 5) is None


def test_a_calendar_window_measures_from_a_close_that_exists() -> None:
    """The base is the last close at or before the cutoff, never the next one after."""
    idx = pd.to_datetime(["2026-08-07", "2026-08-10", "2026-09-11"])
    s = pd.Series([100.0, 200.0, 220.0], index=idx)
    # One month before the 11th is 2026-08-11; the last close at or before that
    # is the 10th, so the base is 200 and not the 7th's 100.
    assert _change_since(s, pd.Timestamp("2026-08-11")) == 10.0


def test_year_to_date_measures_from_the_last_close_of_last_year() -> None:
    """January's first move belongs inside YTD, so the base is December's close."""
    idx = pd.to_datetime(["2025-12-31", "2026-01-02", "2026-09-11"])
    s = pd.Series([100.0, 105.0, 150.0], index=idx)
    assert _change_since(s, pd.Timestamp("2026-01-01"), inclusive=False) == 50.0


def test_a_zero_or_negative_base_yields_nothing_rather_than_dividing() -> None:
    idx = pd.bdate_range(end="2026-09-11", periods=2)
    assert _session_change(pd.Series([0.0, 10.0], index=idx), 1) is None


def test_ranking_runs_best_to_worst() -> None:
    rows = _rank({"XLK": 1.0, "XLE": 5.0, "XLF": -2.0})
    assert [r["sector"] for r in rows] == [
        SECTOR_ETFS["XLE"],
        SECTOR_ETFS["XLK"],
        SECTOR_ETFS["XLF"],
    ]


def test_ranking_drops_sectors_it_could_not_measure() -> None:
    rows = _rank({"XLK": 1.0, "XLE": None})
    assert [r["sector"] for r in rows] == [SECTOR_ETFS["XLK"]]


def test_ties_break_by_name_so_the_order_is_stable() -> None:
    a = _rank({"XLK": 2.0, "XLE": 2.0, "XLF": 2.0})
    b = _rank({"XLF": 2.0, "XLK": 2.0, "XLE": 2.0})
    assert a == b


# --- end to end over a supplied frame ----------------------------------------


def _full_frame() -> pd.DataFrame:
    """All eleven funds, 400 business days, each rising at its own rate."""
    idx = pd.bdate_range(end="2026-09-11", periods=400)
    cols = {}
    for i, etf in enumerate(SECTOR_ETFS):
        cols[etf] = pd.Series([100.0 + i * j / 100.0 for j in range(len(idx))], index=idx)
    return pd.DataFrame(cols)


def test_all_six_windows_come_back_populated() -> None:
    out = _provider(_full_frame()).fetch(DataCategory.SECTOR_PERFORMANCE, "__ALL__")
    assert out is not None
    for field in ("one_day", "five_day", "one_month", "three_month", "ytd", "one_year"):
        rows = getattr(out, field)
        assert len(rows) == 11, f"{field} lost a sector"


def test_realtime_stays_empty_because_daily_closes_are_not_a_live_feed() -> None:
    out = _provider(_full_frame()).fetch(DataCategory.SECTOR_PERFORMANCE, "__ALL__")
    assert out.realtime == [], "claiming an intraday feed this provider does not have"


def test_the_result_states_which_statistic_it_is() -> None:
    out = _provider(_full_frame()).fetch(DataCategory.SECTOR_PERFORMANCE, "__ALL__")
    assert out.source == "spdr_sector_etfs"
    assert "Total return" in out.basis
    assert "not the whole US market" in out.basis


def test_a_missing_sector_is_named_rather_than_quietly_dropped() -> None:
    """Ten sectors presented as eleven is worse than none — it looks complete."""
    frame = _full_frame().drop(columns=["XLE"])
    out = _provider(frame).fetch(DataCategory.SECTOR_PERFORMANCE, "__ALL__")
    assert len(out.one_day) == 10
    assert "Energy" in out.basis
    assert "1 of 11" in out.basis


def test_an_all_nan_column_counts_as_missing_not_as_present() -> None:
    frame = _full_frame()
    frame["XLE"] = float("nan")
    out = _provider(frame).fetch(DataCategory.SECTOR_PERFORMANCE, "__ALL__")
    assert len(out.one_day) == 10
    assert "Energy" in out.basis


def test_the_windows_are_anchored_to_the_data_not_to_today() -> None:
    """A frame ending months ago must still produce a one-day figure.

    Anchoring on `date.today()` would put every cutoff past the end of the
    series — on a weekend or before the open it silently shifts each window by
    a session, and on stale data it empties them.
    """
    idx = pd.bdate_range(end="2026-05-01", periods=400)
    frame = pd.DataFrame(
        {etf: pd.Series(range(1, 401), index=idx, dtype=float) for etf in SECTOR_ETFS}
    )
    out = _provider(frame).fetch(DataCategory.SECTOR_PERFORMANCE, "__ALL__")
    assert len(out.one_day) == 11
    assert len(out.one_year) == 11


def test_no_prices_at_all_is_unavailable_not_a_flat_market() -> None:
    assert _provider(pd.DataFrame()).fetch(DataCategory.SECTOR_PERFORMANCE, "__ALL__") is None


def test_a_download_failure_is_reported_as_unavailable() -> None:
    p = SectorETFProvider()

    def _boom(tickers, days):
        raise RuntimeError("network down")

    p._download_closes = _boom  # type: ignore[method-assign]
    assert p.fetch(DataCategory.SECTOR_PERFORMANCE, "__ALL__") is None


def test_the_ranking_actually_orders_by_return() -> None:
    """Three funds with hand-set moves; the order must follow the arithmetic."""
    frame = _frame(
        {
            "XLK": [100.0, 90.0],  # -10%
            "XLE": [100.0, 130.0],  # +30%
            "XLF": [100.0, 105.0],  # +5%
        }
    )
    out = _provider(frame).fetch(DataCategory.SECTOR_PERFORMANCE, "__ALL__")
    assert [r.sector for r in out.one_day] == ["Energy", "Financials", "Information Technology"]
    assert [r.change_pct for r in out.one_day] == [30.0, 5.0, -10.0]


# --- the provider is wired into the chain ------------------------------------


def test_it_is_registered_and_beats_the_retired_alpha_vantage_endpoint() -> None:
    from hedge_fund.data.registry import ProviderRegistry

    # `get_chain` returns provider names, in the order they will be tried.
    names = list(ProviderRegistry().get_chain(DataCategory.SECTOR_PERFORMANCE))
    assert "sector_etfs" in names, "sector drift has no provider in the chain"
    if "alpha_vantage" in names:
        assert names.index("sector_etfs") < names.index("alpha_vantage")


@pytest.mark.parametrize("etf,sector", list(SECTOR_ETFS.items()))
def test_sector_names_are_spelled_as_gics_spells_them(etf: str, sector: str) -> None:
    """These join up with a company's `sector` field, so spelling is a contract."""
    assert sector == sector.strip()
    assert sector[0].isupper()
