"""Placing a return series on the growth/inflation map.

A point's two coordinates are *partial* correlations: its inflation
sensitivity is measured holding growth news fixed, and its growth sensitivity
holding inflation news fixed. Simple correlations would not do, because the two
metrics are not quite independent, and an asset that only ever responded to
growth would pick up a spurious inflation reading through that overlap.

The honest part of this module is :func:`_uncertainty`. The returns are
overlapping 12-month windows read off quarterly, so 218 quarters carry roughly
54 independent years of information, and a correlation estimated on 54
observations has a standard error near 0.14. Two points a tenth apart are the
same point. Everything returned here carries that number so the UI can say so.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from hedge_fund.macro import news

Number = float | None


class NotEnoughHistory(ValueError):
    """Fewer usable quarters than :data:`news.MIN_QUARTERS`."""


# ── aligning a series to the quarterly grid ───────────────────────────────


def _quarter_last_month(quarter: str) -> str:
    """``"1972Q1"`` -> ``"1972-03"``, the month a quarter's 12-month window ends."""
    year, q = quarter.split("Q")
    return f"{int(year):04d}-{3 * int(q):02d}"


def _shift_month(month: str, back: int) -> str:
    year, m = (int(part) for part in month.split("-"))
    total = year * 12 + (m - 1) - back
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def from_monthly(months: Sequence[str], returns: Sequence[Number]) -> list[Number]:
    """Compound monthly returns into the 12-month figure at each quarter end.

    Months are matched by label rather than by position, so a series that
    starts late or has a gap lands on the right quarters instead of being
    silently slid along the axis. A window missing any of its twelve months is
    ``None``: a partial year compared against a full one is a different
    statistic wearing the same name.
    """
    by_month = {
        m: r for m, r in zip(months, returns, strict=True) if r is not None and math.isfinite(r)
    }
    out: list[Number] = []
    for quarter in news.quarters():
        end = _quarter_last_month(quarter)
        window = [by_month.get(_shift_month(end, back)) for back in range(11, -1, -1)]
        if any(v is None for v in window):
            out.append(None)
            continue
        gross = 1.0
        for v in window:
            gross *= 1.0 + float(v)  # type: ignore[arg-type]
        out.append(gross - 1.0)
    return out


# ── the statistic ─────────────────────────────────────────────────────────


def _partial(xy: float, xz: float, yz: float) -> float:
    """Correlation of x and y with z held fixed."""
    denominator = math.sqrt((1.0 - xz**2) * (1.0 - yz**2))
    if denominator <= 0.0:
        return 0.0
    return (xy - xz * yz) / denominator


def _uncertainty(n_quarters: int) -> tuple[float, float]:
    """Independent years behind ``n_quarters``, and the standard error that implies.

    Fisher's 1/sqrt(n - 3) on the *effective* count, not the quarter count.
    Using the quarter count would halve the error bar for free and is the
    single easiest way to make a map like this look more certain than it is.
    """
    effective = n_quarters / news.OVERLAP
    return effective, 1.0 / math.sqrt(max(effective - 3.0, 1.0))


def sensitivity(returns: Sequence[Number]) -> dict[str, Any]:
    """The two partial correlations for one series already on the quarter grid.

    Raises :class:`NotEnoughHistory` rather than returning a number nobody
    should read — a series with six years of overlap can produce a perfectly
    confident-looking 0.6.
    """
    quarters = news.quarters()
    if len(returns) != len(quarters):
        raise ValueError(f"expected {len(quarters)} quarters, got {len(returns)}")

    inflation = news.metric("inflation")
    growth = news.metric("growth")
    keep = [
        i
        for i, r in enumerate(returns)
        if r is not None and math.isfinite(r) and inflation[i] is not None and growth[i] is not None
    ]
    if len(keep) < news.MIN_QUARTERS:
        raise NotEnoughHistory(
            f"{len(keep)} usable quarters, {news.MIN_QUARTERS} needed "
            f"({news.MIN_QUARTERS // news.OVERLAP} independent years)"
        )

    r = np.array([returns[i] for i in keep], dtype=np.float64)
    i_news = np.array([inflation[i] for i in keep], dtype=np.float64)
    g_news = np.array([growth[i] for i in keep], dtype=np.float64)

    r_ri = float(np.corrcoef(r, i_news)[0, 1])
    r_rg = float(np.corrcoef(r, g_news)[0, 1])
    r_ig = float(np.corrcoef(i_news, g_news)[0, 1])

    years, error = _uncertainty(len(keep))
    to_inflation = round(_partial(r_ri, r_rg, r_ig), 3)
    to_growth = round(_partial(r_rg, r_ri, r_ig), 3)
    return {
        "inflation": to_inflation,
        "growth": to_growth,
        "quadrant": quadrant(to_inflation, to_growth),
        "quarters": len(keep),
        "independent_years": round(years, 1),
        "standard_error": round(error, 3),
        "from": quarters[keep[0]],
        "to": quarters[keep[-1]],
    }


def quadrant(inflation: float, growth: float) -> str:
    """The macro environment a point is positioned to enjoy.

    The names are AQR's, and they describe the environment rather than the
    asset: a series in "stagflation" is one whose good years have been the
    ones with rising inflation and falling growth.
    """
    if growth >= 0:
        return "overheating" if inflation >= 0 else "goldilocks"
    return "stagflation" if inflation >= 0 else "recession"


# ── the points on the map ─────────────────────────────────────────────────


def _point(label: str, kind: str, returns: Sequence[Number], **extra: Any) -> dict[str, Any] | None:
    try:
        got = sensitivity(returns)
    except NotEnoughHistory:
        return None
    got.update(label=label, kind=kind, **extra)
    return got


def reference_points() -> list[dict[str, Any]]:
    """The market, the 10-year, 60/40 and Kenneth French's industries."""
    points = []
    for series in news.reference_series():
        point = _point(
            series["label"], series["kind"], series["returns"], id=series["id"], note=series["note"]
        )
        if point is not None:
            points.append(point)
    return points


def factor_points() -> list[dict[str, Any]]:
    """The JKP long-short themes, from the file the Factors tab already reads.

    They belong on this map for a reason worth stating: a long-short portfolio
    has most of the market's direction netted out of it, so if anything in this
    repo sits near the origin — the diversifier corner of AQR's exhibit — it
    will be these. Whether it does is a question, not an assumption, which is
    why they are computed here rather than asserted anywhere.
    """
    from hedge_fund.factors import jkp

    try:
        data = jkp.load()
    except jkp.FactorDataMissing:
        return []

    months = data["months"]
    points = []
    for theme_id, theme in data["themes"].items():
        start = theme["start"]
        window = months[start : start + len(theme["returns"])]
        point = _point(
            theme_id.replace("_", " "),
            "factor",
            from_monthly(window, theme["returns"]),
            id=f"jkp_{theme_id}",
            note=f"JKP long-short theme, {theme['n_factors']} factors.",
        )
        if point is not None:
            points.append(point)
    return points
