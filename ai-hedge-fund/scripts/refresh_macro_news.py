"""Rebuild the macro news file the growth/inflation map reads.

Run from the repo root:

    uv run --with openpyxl python scripts/refresh_macro_news.py

WHAT IT BUILDS

Two US macroeconomic "news" series — one for inflation, one for growth — at
quarterly frequency from 1972, plus the reference return series the map needs
to have anything to plot against them. All of it lands in one committed,
dated JSON file so the API answers offline, the same arrangement as the JKP
factor file next door.

THE METHOD IS AQR'S

Following AQR, *Alternative Thinking* 2026 Issue 3, "Inflation Redux?",
Exhibit 4, which in turn follows Brixton, Maloney and Thapar (2021). Asset
prices already reflect the inflation everyone expects, so a sensitivity
measured against the *level* of inflation mostly measures nothing. What moves
prices is the news, and they take the news to be an equal-risk blend of two
imperfect measures of it:

    change   = year-on-year rate  -  the same rate 12 months earlier
    surprise = year-on-year rate  -  the 1-year forecast made a year earlier

The first assumes expectations follow a random walk, the second asks the
forecasters. Neither is right; averaging them cancels some of the noise in
each. "Equal-risk" is the standardisation below: divide each leg by its own
standard deviation before averaging, so the blend is not quietly dominated by
whichever leg happens to be more volatile.

Quarterly overlapping year-on-year windows are their choice too, and it is the
right one: it sidesteps seasonal adjustment arguments and it absorbs the
publication lag, since GDP for a quarter is not known until well into the next.

WHAT IS OURS, AND WHERE IT DIFFERS FROM THEIRS

Their proxies are Bloomberg index series we have no licence for. Everything
here is free and keyless:

  * realised inflation and growth — FRED CPIAUCSL and GDPC1
  * forecasts — the Philadelphia Fed's Survey of Professional Forecasters
  * the equity market and industries — Kenneth French's data library
  * the 10-year Treasury — a total return built from FRED DGS10, see below

Two consequences worth stating rather than burying. The SPF has no CPI
forecast before 1981Q3, so the inflation surprise leg splices the GDP deflator
forecast behind it — a different price index, and the file records where the
join is. And the Treasury total return is a duration approximation from the
constant-maturity yield, not an index: good enough for a correlation, and
visibly not a return series anyone should quote.

The assets AQR plot that carry their actual argument — commodities, gold,
inflation-linked bonds, credit, trend — all need licensed series. They are
absent here rather than approximated from something that merely looks similar.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("refresh_macro_news")

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "macro"
OUT_FILE = OUT_DIR / "us-macro-news.json"

SPF_URL = (
    "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/"
    "survey-of-professional-forecasters/historical-data/medianlevel.xlsx"
)

#: AQR's own start. Earlier data exists but the trade-off they describe — more
#: history against better data — lands here, and staying on their window keeps
#: our numbers comparable to their published ones.
START = date(1970, 1, 1)
FIRST_QUARTER = "1972Q1"

#: French's 12 industries, which stand in for the GICS sectors AQR use. The
#: SPDR sector ETFs would be closer to GICS and are already in this repo, but
#: they start in 1999 (2015 for real estate, 2018 for communications) — a
#: handful of independent year-long windows, which is not a point on a map.
INDUSTRY_LABELS = {
    "NoDur": "Consumer non-durables",
    "Durbl": "Consumer durables",
    "Manuf": "Manufacturing",
    "Enrgy": "Energy",
    "Chems": "Chemicals",
    "BusEq": "Business equipment",
    "Telcm": "Telecoms",
    "Utils": "Utilities",
    "Shops": "Shops",
    "Hlth": "Health",
    "Money": "Financials",
    # "Other" is French's residual bucket — everything that fits nowhere else.
    # It has no economic reading, so it would be a point nobody could interpret.
}


class RefreshError(RuntimeError):
    """A source did not answer, or answered with something unusable."""


# ── macro news ────────────────────────────────────────────────────────────


def _fred(series_id: str) -> pd.Series:
    import pandas_datareader as pdr

    df = pdr.DataReader(series_id, "fred", START, date.today())
    if df.empty:
        raise RefreshError(f"FRED returned nothing for {series_id}")
    return df[series_id].dropna()


def _quarterly_yoy(s: pd.Series, average_first: bool) -> pd.Series:
    """Year-on-year change of a series, on a quarterly index.

    ``average_first`` is for monthly series like CPI: the quarter's value is
    the average of its three months, not the last one, so a single noisy print
    does not set the quarter.
    """
    if average_first:
        s = s.resample("QE").mean()
    s.index = pd.PeriodIndex(s.index, freq="Q")
    return s / s.shift(4) - 1.0


def _spf_sheets(path: Path) -> dict[str, pd.DataFrame]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    out: dict[str, pd.DataFrame] = {}
    for name in ("CPI", "RGDP", "PGDP"):
        rows = list(wb[name].iter_rows(values_only=True))
        df = pd.DataFrame(rows[1:], columns=rows[0]).replace("#N/A", np.nan)
        df.index = pd.PeriodIndex(
            [pd.Period(f"{int(y)}Q{int(q)}") for y, q in zip(df["YEAR"], df["QUARTER"], strict=True)],
            freq="Q",
        )
        out[name] = df.apply(pd.to_numeric, errors="coerce")
    return out


def _forecasts(spf: dict[str, pd.DataFrame]) -> tuple[pd.Series, pd.Series, str | None]:
    """Expected inflation and growth over the four quarters after each survey.

    The SPF numbers each quarter's forecasts from the survey quarter itself, so
    columns 2 through 5 are the next four quarters. CPI arrives as annualised
    quarterly rates, which average to the year; RGDP arrives as levels, so the
    year is the ratio of the two ends.
    """
    cpi, rgdp, pgdp = spf["CPI"], spf["RGDP"], spf["PGDP"]
    from_cpi = cpi[["CPI2", "CPI3", "CPI4", "CPI5"]].mean(axis=1) / 100.0
    from_deflator = pgdp["PGDP5"] / pgdp["PGDP1"] - 1.0

    joined = from_cpi.combine_first(from_deflator)
    first_cpi = from_cpi.dropna()
    splice = str(first_cpi.index.min()) if not first_cpi.empty else None

    growth = rgdp["RGDP5"] / rgdp["RGDP1"] - 1.0
    return joined.dropna(), growth.dropna(), splice


def _news(realised: pd.Series, forecast: pd.Series) -> pd.DataFrame:
    """The two legs and their equal-risk blend, standardised.

    Each leg is divided by its own standard deviation before averaging, which
    is what makes the blend equal-*risk* rather than equal-weight, and the
    result is restandardised so a sensitivity reads as a correlation.
    """
    df = pd.concat(
        [
            (realised - realised.shift(4)).rename("change"),
            (realised - forecast.shift(4)).rename("surprise"),
        ],
        axis=1,
    ).dropna()
    if df.empty:
        raise RefreshError("no quarters where both news legs exist")
    blend = (df / df.std()).mean(axis=1)
    df["news"] = (blend - blend.mean()) / blend.std()
    return df


# ── the series the map plots against them ─────────────────────────────────


def _french(dataset: str) -> pd.DataFrame:
    import pandas_datareader as pdr

    got = pdr.DataReader(dataset, "famafrench", START, date.today())[0] / 100.0
    got.index = pd.PeriodIndex(got.index, freq="M")
    # French marks missing months -99.99, which becomes -0.9999 after the
    # division above and would read as a month that lost everything.
    return got.where(got > -0.99)


def _treasury_total_return() -> pd.Series:
    """Monthly total return of a rolling 10-year par Treasury, from its yield.

    Carry for the month plus the price move a duration approximation implies:

        r = y/12 - D * dy

    with D the modified duration of a par bond at last month's yield. It
    ignores convexity and the roll down the curve, both small at monthly
    horizons next to the yield move itself. It exists because no free source
    publishes a Treasury total-return index back to 1972, and a correlation
    against a slightly wrong bond is far better than no bond on the map.
    """
    y = _fred("DGS10").resample("ME").last() / 100.0
    y.index = pd.PeriodIndex(y.index, freq="M")
    prev = y.shift(1)
    # Modified duration of a 10-year par bond, semiannual coupons.
    duration = (1 - (1 + prev / 2) ** -20) / (prev / 2) / (1 + prev / 2)
    return (prev / 12 - duration * (y - prev)).dropna()


def _rolling_12m(monthly: pd.Series, quarters: pd.PeriodIndex) -> list[float | None]:
    """Compounded 12-month return, read off at each quarter end."""
    gross = (1 + monthly).rolling(12).apply(np.prod, raw=True) - 1
    at_quarter = gross.resample("Q").last().reindex(quarters)
    return [None if not np.isfinite(v) else round(float(v), 6) for v in at_quarter]


# ── assembly ──────────────────────────────────────────────────────────────


def build(spf_path: Path) -> dict[str, Any]:
    log.info("FRED: CPIAUCSL, GDPC1, DGS10")
    inflation = _quarterly_yoy(_fred("CPIAUCSL"), average_first=True)
    growth = _quarterly_yoy(_fred("GDPC1"), average_first=False)

    log.info("SPF: %s", spf_path.name)
    spf = _spf_sheets(spf_path)
    f_inflation, f_growth, cpi_from = _forecasts(spf)

    infl_news = _news(inflation, f_inflation)
    grow_news = _news(growth, f_growth)

    quarters = infl_news.index.intersection(grow_news.index)
    quarters = quarters[quarters >= pd.Period(FIRST_QUARTER)]
    if len(quarters) < 40:
        raise RefreshError(f"only {len(quarters)} quarters of news — a source is short")
    log.info("news: %s to %s (%d quarters)", quarters.min(), quarters.max(), len(quarters))

    def leg(df: pd.DataFrame, col: str) -> list[float]:
        return [round(float(v), 6) for v in df.loc[quarters, col]]

    log.info("Kenneth French: market and 12 industries")
    ff = _french("F-F_Research_Data_Factors")
    market = ff["Mkt-RF"] + ff["RF"]
    treasury = _treasury_total_return()
    sixty_forty = (0.6 * market + 0.4 * treasury).dropna()

    series: list[dict[str, Any]] = [
        {
            "id": "us_equity",
            "label": "US equity market",
            "kind": "anchor",
            "note": "Kenneth French's US market return, dividends included.",
            "returns": _rolling_12m(market, quarters),
        },
        {
            "id": "us_treasury_10y",
            "label": "US 10y Treasury",
            "kind": "anchor",
            "note": "Duration approximation from the FRED constant-maturity yield, not an index.",
            "returns": _rolling_12m(treasury, quarters),
        },
        {
            "id": "us_60_40",
            "label": "US 60/40",
            "kind": "anchor",
            "note": "60% the market, 40% the 10-year, rebalanced monthly.",
            "returns": _rolling_12m(sixty_forty, quarters),
        },
    ]

    industries = _french("12_Industry_Portfolios")
    for column in industries.columns:
        label = INDUSTRY_LABELS.get(column.strip())
        if label is None:
            continue
        series.append(
            {
                "id": f"industry_{column.strip().lower()}",
                "label": label,
                "kind": "industry",
                "note": "One of Kenneth French's 12 industry portfolios, value-weighted.",
                "returns": _rolling_12m(industries[column], quarters),
            }
        )
    log.info("series: %d (%d industries)", len(series), len(series) - 3)

    return {
        "source": {
            "method": (
                "AQR, Alternative Thinking 2026 Issue 3, 'Inflation Redux?', Exhibit 4, "
                "following Brixton, Maloney and Thapar (2021)."
            ),
            "realised": "FRED: CPIAUCSL (quarterly average), GDPC1, DGS10.",
            "forecasts": f"Philadelphia Fed Survey of Professional Forecasters, medians ({SPF_URL}).",
            "returns": "Kenneth French data library, via pandas-datareader.",
        },
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "quarters": [str(q) for q in quarters],
        "inflation": {
            "change": leg(infl_news, "change"),
            "surprise": leg(infl_news, "surprise"),
            "news": leg(infl_news, "news"),
            "realised": [round(float(v), 6) for v in inflation.reindex(quarters)],
            "forecast_splice": (
                f"SPF CPI forecasts begin {cpi_from}; the GDP deflator forecast stands in before that."
                if cpi_from
                else None
            ),
        },
        "growth": {
            "change": leg(grow_news, "change"),
            "surprise": leg(grow_news, "surprise"),
            "news": leg(grow_news, "news"),
            "realised": [round(float(v), 6) for v in growth.reindex(quarters)],
            "forecast_splice": None,
        },
        "series": series,
        "absent": (
            "Commodities, gold, inflation-linked bonds, credit and trend-following carry "
            "AQR's argument about what does hedge inflation. Each needs a licensed index "
            "with no free equivalent back to 1972, so none is plotted here."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--spf",
        type=Path,
        help="a medianlevel.xlsx already on disk; downloaded from the Philadelphia Fed if omitted",
    )
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    spf_path = args.spf
    if spf_path is None:
        spf_path = OUT_DIR / ".spf-medianlevel.xlsx"
        log.info("downloading %s", SPF_URL)
        try:
            urllib.request.urlretrieve(SPF_URL, spf_path)  # noqa: S310 — a fixed https URL
        except OSError as exc:
            log.error("could not fetch the SPF file: %s", exc)
            return 1

    try:
        payload = build(spf_path)
    except RefreshError as exc:
        log.error("%s", exc)
        return 1

    OUT_FILE.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    log.info("wrote %s (%.0f KB)", OUT_FILE.relative_to(ROOT), OUT_FILE.stat().st_size / 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
