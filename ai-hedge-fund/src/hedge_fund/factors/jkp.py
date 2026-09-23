"""The JKP factor returns, and the few statistics worth computing over them.

The data is the authors' — US, monthly, capped value-weighted long-short
portfolios for 153 characteristics grouped into 13 themes — reshaped by
`scripts/refresh_jkp.py` into one committed JSON file. This module only reads
it and does arithmetic, so every figure it returns can be re-derived from their
CSV.

The statistic that carries the paper's argument is the split around each
factor's original sample. A factor that earned a premium in the years its
discoverer studied, and kept earning one afterwards, replicated; one that only
worked in-sample is the kind of result the replication-crisis literature is
about. `factor_rows` computes both halves so the screen can draw the pair
rather than one flattering full-sample number.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "factors"
RETURNS_FILE = DATA_DIR / "jkp-usa-monthly-vw_cap.json"
DETAILS_FILE = DATA_DIR / "jkp-factor-details.json"

#: The order the themes are drawn in. The paper's own figures group them this
#: way — the classic anomalies first, the harder-to-trade ones last — and a
#: fixed order means a theme is always in the same row, whatever its numbers.
THEME_ORDER = (
    "value",
    "momentum",
    "quality",
    "profitability",
    "investment",
    "low_risk",
    "low_leverage",
    "size",
    "accruals",
    "debt_issuance",
    "profit_growth",
    "short_term_reversal",
    "seasonality",
)

#: Fewer months than this and a Sharpe ratio is noise with a decimal point.
MIN_MONTHS = 24


class FactorDataMissing(RuntimeError):
    """The committed JKP file is absent. Rebuild it with scripts/refresh_jkp.py."""


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    try:
        data = json.loads(RETURNS_FILE.read_text(encoding="utf-8"))
        details = json.loads(DETAILS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FactorDataMissing(str(exc)) from exc
    data["details"] = details
    return data


def stats(returns: list[float | None]) -> dict[str, Any] | None:
    """Annualised mean, volatility, Sharpe and t-statistic of monthly returns.

    Missing months are skipped rather than read as zero. Below `MIN_MONTHS`
    the answer is None, not a number: two years is already a thin sample for a
    long-short portfolio, and anything shorter is a coin toss reported to two
    decimal places.
    """
    xs = [r for r in returns if r is not None and math.isfinite(r)]
    n = len(xs)
    if n < MIN_MONTHS:
        return None
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    sd = math.sqrt(var)
    return {
        "months": n,
        "ann_return": mean * 12,
        "ann_vol": sd * math.sqrt(12),
        "sharpe": (mean / sd) * math.sqrt(12) if sd > 0 else None,
        "t_stat": mean / (sd / math.sqrt(n)) if sd > 0 else None,
    }


def _window(
    series: dict[str, Any], months: list[str], lo: str | None = None, hi: str | None = None
) -> list[float | None]:
    """The part of a series whose months fall in [lo, hi], as 'YYYY-MM' strings."""
    start = series["start"]
    out = []
    for i, r in enumerate(series["returns"]):
        m = months[start + i]
        if (lo is None or m >= lo) and (hi is None or m <= hi):
            out.append(r)
    return out


def _windows(series: dict[str, Any], months: list[str]) -> dict[str, Any]:
    last = months[series["start"] + len(series["returns"]) - 1]
    y, mo = int(last[:4]), int(last[5:7])
    ten_back = f"{y - 10:04d}-{mo:02d}"
    year_back = f"{y - 1:04d}-{mo:02d}"
    trailing = [r for r in _window(series, months, lo=year_back) if r is not None][1:]
    return {
        "full": stats(series["returns"]),
        "since_2000": stats(_window(series, months, lo="2000-01")),
        "last_10y": stats(_window(series, months, lo=ten_back)[1:]),
        # Twelve months is too short for a Sharpe ratio (see MIN_MONTHS), so
        # the trailing year is reported as what it is: a compounded return.
        "last_12m_return": (math.prod(1 + r for r in trailing) - 1)
        if len(trailing) == 12
        else None,
    }


def coverage() -> dict[str, Any]:
    d = load()
    return {
        "source": d["source"],
        "region": d["region"],
        "frequency": d["frequency"],
        "weighting": d["weighting"],
        "built_at": d["built_at"],
        "first_month": d["months"][0],
        "last_month": d["months"][-1],
    }


def theme_rows() -> dict[str, Any]:
    """Every theme with its monthly returns and summary statistics."""
    d = load()
    months = d["months"]
    names = d["details"]["themes"]
    themes = []
    for tid in THEME_ORDER:
        s = d["themes"].get(tid)
        if s is None:
            continue
        themes.append(
            {
                "id": tid,
                "name": names.get(tid, tid),
                "n_factors": s["n_factors"],
                "start": s["start"],
                "returns": s["returns"],
                "stats": _windows(s, months),
            }
        )
    return {**coverage(), "months": months, "themes": themes}


def factor_rows(theme: str) -> dict[str, Any] | None:
    """The factors inside one theme, each split around its original sample.

    `in_sample` is the window the original paper studied; `post_sample` is
    everything after it ends. Where the two disagree in sign, the published
    result did not survive — which is the paper's question, asked per factor.
    """
    d = load()
    if theme not in d["themes"]:
        return None
    months = d["months"]
    details = d["details"]["factors"]
    rows = []
    for fid, s in d["factors"].items():
        meta = details.get(fid)
        if not meta or meta["theme"] != theme:
            continue
        sample = meta.get("in_sample")
        ins = post = None
        if sample:
            lo, hi = f"{sample[0]:04d}-01", f"{sample[1]:04d}-12"
            ins = stats(_window(s, months, lo=lo, hi=hi))
            post = stats(_window(s, months, lo=f"{sample[1] + 1:04d}-01"))
        rows.append(
            {
                "id": fid,
                "name": meta["name"],
                "cite": meta.get("cite"),
                "in_sample_years": sample,
                "original_t": meta.get("original_t"),
                # +1: long the high end of the characteristic. -1: long the low
                # end (small caps, low asset growth). The returns are already
                # signed this way, so a positive mean is always "worked".
                "direction": s["direction"],
                "full": stats(s["returns"]),
                "in_sample": ins,
                "post_sample": post,
            }
        )
    rows.sort(key=lambda r: -((r["post_sample"] or r["full"] or {}).get("sharpe") or -99))
    return {
        **coverage(),
        "theme": {"id": theme, "name": d["details"]["themes"].get(theme, theme)},
        "factors": rows,
    }
