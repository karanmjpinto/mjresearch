"""Sector drift, computed from the SPDR Select Sector ETFs.

Alpha Vantage used to hand this over as a finished ranking. That endpoint is
retired — it answers `function=SECTOR` with a bare `{}` on a valid key — and
every free replacement surveyed was worse than doing the arithmetic here:

  - Yahoo's own GICS sector indices (`^SP500-45` and friends) stopped updating
    in July 2026 while still serving a current timestamp, which is the most
    dangerous failure mode available: plausible, stale, and silent.
  - The vendors that still publish a "sector performance" figure mostly publish
    the *average change across constituents*, which is a different statistic
    from an index return and is dominated by small caps. One such source had
    Technology up 85.74% over a year where the cap-weighted answer was 39.67%.
    Both are labelled "technology sector, 1 year".

So this computes the ranking from prices, which means this file owns the
definition: which fund stands for which sector, whether dividends count, and
what "one month" means. Those are stated below rather than left implicit, which
is the entire advantage of computing it — a retired endpoint cannot take the
panel down again, and the number can be audited.

What it is, stated precisely: the total return of the eleven S&P 500 sector
sleeves. Not the whole US market. Anyone expecting "technology" to span every
listed tech company will read these as low, which is why the API labels the
result rather than leaving the caller to guess.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from hedge_fund.data.cache import DataCategory
from hedge_fund.data.models import SectorPerformance
from hedge_fund.data.providers.base import BaseProvider

logger = logging.getLogger(__name__)

#: Ticker → sector name. The SPDR Select Sector suite maps one-to-one onto the
#: eleven GICS sectors, which is why it is used here rather than a family that
#: nearly does: Vanguard's sector funds are ten, with mismatched benchmarks
#: (VNQ tracks a real-estate index, not a GICS sleeve). Fidelity's MSCI suite is
#: arguably the more correct all-cap proxy; these win on being the set every
#: sector-rotation discussion already quotes, so the figures here match what a
#: reader sees elsewhere.
#:
#: Names are spelled as GICS spells them, so they join up with the `sector`
#: field on a company's fundamentals without a translation table.
SECTOR_ETFS: dict[str, str] = {
    "XLK": "Information Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}

#: Calendar days of history to pull. The longest window is one year, and the
#: year-to-date window needs the last close of the previous year, so a year plus
#: a buffer for holidays covers everything. Kept tight because the whole panel
#: is one batched request and there is no reason to move five years of bars.
LOOKBACK_DAYS = 500

#: Sessions, not calendar days, for the two short windows: "5 day" has always
#: meant five trading sessions, and over a holiday week the calendar reading
#: would quietly compare four sessions instead. The longer windows below are
#: calendar-anchored, because "one month" does mean a month to a reader.
SESSION_WINDOWS: dict[str, int] = {"one_day": 1, "five_day": 5}

#: Calendar offsets for the longer windows, each resolved to the last close at
#: or before the anchor date.
MONTH_WINDOWS: dict[str, int] = {"one_month": 1, "three_month": 3, "one_year": 12}

#: How the result describes itself. Read by the API and shown in the UI, so the
#: reader is told which statistic this is rather than inferring it.
SOURCE = "spdr_sector_etfs"
BASIS = (
    "Total return of the eleven S&P 500 sector ETFs, dividends reinvested. "
    "Large-cap sector sleeves, not the whole US market."
)


class SectorETFProvider(BaseProvider):
    """Sector performance derived from sector ETF closes. No API key."""

    name = "sector_etfs"
    #: Ahead of Alpha Vantage (4), whose sector endpoint no longer answers, and
    #: behind nothing — this needs no key, so it is always the first thing tried
    #: for the category.
    priority = 2
    categories = {DataCategory.SECTOR_PERFORMANCE}

    def available(self) -> bool:
        return True  # yfinance needs no API key

    def fetch(self, category: DataCategory, ticker: str, **kwargs: Any) -> Any:
        if category != DataCategory.SECTOR_PERFORMANCE:
            return None
        return self._sector_performance(**kwargs)

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def _download_closes(self, tickers: list[str], days: int) -> pd.DataFrame:
        """Adjusted daily closes, one column per ticker.

        Split out so a test can supply a frame instead of reaching the network.

        `auto_adjust=True` is the load-bearing argument. On price returns the
        dividend drag is nil at a day or a week and decisive at a year: measured
        against total return, Energy is understated by 4.56 percentage points
        and Technology by 0.73. A spread that wide reorders the ranking, so a
        price-return column would not merely be imprecise, it would put the
        sectors in the wrong order.
        """
        import yfinance as yf

        raw = yf.download(
            tickers,
            period=f"{days}d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if raw is None or raw.empty:
            return pd.DataFrame()

        # One ticker comes back flat, several come back as (field, ticker).
        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" not in raw.columns.get_level_values(0):
                return pd.DataFrame()
            closes = raw["Close"]
        else:
            if "Close" not in raw.columns:
                return pd.DataFrame()
            closes = raw[["Close"]].rename(columns={"Close": tickers[0]})

        return closes.sort_index()

    def _sector_performance(self, **kwargs: Any) -> SectorPerformance | None:
        days = int(kwargs.get("days", LOOKBACK_DAYS))
        try:
            closes = self._download_closes(list(SECTOR_ETFS), days)
        except Exception as e:
            logger.warning("Sector ETF download failed: %s", e)
            return None

        if closes.empty:
            logger.warning("Sector ETF download returned no closes")
            return None

        series = {
            etf: closes[etf].dropna()
            for etf in SECTOR_ETFS
            if etf in closes.columns and closes[etf].notna().any()
        }
        if not series:
            logger.warning("No sector ETF returned a usable price series")
            return None

        # Never silently partial: a ten-sector ranking presented as eleven is
        # worse than none, because it looks complete. So a gap is logged for
        # whoever is debugging and carried in `basis` for whoever is reading.
        missing = sorted(set(SECTOR_ETFS) - set(series))
        basis = BASIS
        if missing:
            gap = ", ".join(SECTOR_ETFS[m] for m in missing)
            logger.warning(
                "Sector drift is missing %d of %d sectors: %s",
                len(missing),
                len(SECTOR_ETFS),
                ", ".join(f"{m} ({SECTOR_ETFS[m]})" for m in missing),
            )
            basis = (
                f"{BASIS} {len(missing)} of {len(SECTOR_ETFS)} sectors are "
                f"missing from this reading: {gap}."
            )

        # The most recent observation, not the wall clock, anchors every window.
        # On a Sunday, or before the US open, `date.today()` would place the
        # anchor on a day with no close and shift each window by a session.
        anchor = max(s.index[-1] for s in series.values())

        periods: dict[str, list[dict[str, Any]]] = {}
        for field, sessions in SESSION_WINDOWS.items():
            periods[field] = _rank({etf: _session_change(s, sessions) for etf, s in series.items()})
        for field, months in MONTH_WINDOWS.items():
            cutoff = anchor - pd.DateOffset(months=months)
            periods[field] = _rank({etf: _change_since(s, cutoff) for etf, s in series.items()})

        # Year to date is measured from the last close of the previous year, not
        # from the first close of this one: the move on the first trading day of
        # January belongs inside YTD.
        year_start = pd.Timestamp(year=anchor.year, month=1, day=1, tz=anchor.tz)
        periods["ytd"] = _rank(
            {etf: _change_since(s, year_start, inclusive=False) for etf, s in series.items()}
        )

        return SectorPerformance(
            # `realtime` stays empty on purpose. Daily closes give exactly one
            # latest move and that is `one_day`; filling both from the same
            # figure would claim an intraday feed this does not have.
            one_day=periods["one_day"],
            five_day=periods["five_day"],
            one_month=periods["one_month"],
            three_month=periods["three_month"],
            ytd=periods["ytd"],
            one_year=periods["one_year"],
            source=SOURCE,
            basis=basis,
        )


# ------------------------------------------------------------------
# Period arithmetic
# ------------------------------------------------------------------


def _pct(base: float, last: float) -> float | None:
    """Percentage change, or None where the base cannot support one."""
    if base is None or last is None:
        return None
    if not (base > 0):
        return None
    return round((last / base - 1.0) * 100.0, 4)


def _session_change(s: pd.Series, sessions: int) -> float | None:
    """Change over a number of trading sessions."""
    if len(s) <= sessions:
        return None
    return _pct(float(s.iloc[-(sessions + 1)]), float(s.iloc[-1]))


def _change_since(s: pd.Series, cutoff: pd.Timestamp, *, inclusive: bool = True) -> float | None:
    """Change from the last close at (or before) `cutoff` to the latest close.

    A window is measured from a close that actually exists. Anchoring on the
    first close *after* the cutoff instead would shorten every window by
    whatever holiday happened to fall there, and shorten them by different
    amounts for different sectors.

    `inclusive=False` is for year-to-date, where the base must fall strictly
    before January 1st rather than on it.
    """
    prior = s.loc[s.index <= cutoff] if inclusive else s.loc[s.index < cutoff]
    if prior.empty:
        # Not enough history — XLRE begins in 2015 and XLC in 2018, so this only
        # fires for windows longer than this provider offers, or for a fund too
        # new for the window asked about.
        return None
    return _pct(float(prior.iloc[-1]), float(s.iloc[-1]))


def _rank(changes: dict[str, float | None]) -> list[dict[str, Any]]:
    """Best to worst, which is the order these are read in.

    The order is information, and it is the reason the wire format is a list of
    rows rather than a mapping: a sector's rank against its peers is most of
    what anyone wants from this panel.
    """
    rows = [
        {"sector": SECTOR_ETFS[etf], "change_pct": pct}
        for etf, pct in changes.items()
        if pct is not None
    ]
    rows.sort(key=lambda r: (-r["change_pct"], r["sector"]))
    return rows
