"""Market breadth and the divergence test over it.

Computed, not judged: no model is called, so there is no spend guard and the
answer is identical for identical inputs. The expensive part — five hundred
price histories — is not here at all; it is built ahead of time by
``scripts/refresh_breadth.py`` and this route reads the result, so the only
work per request is a few thousand rows of numpy.

The thresholds are query parameters rather than constants because the honest
finding on this screen is how much the answer moves when they change. A screen
that hardcoded one pair of numbers would be presenting one arbitrary choice as
a fact.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from hedge_fund.breadth import (
    BreadthDataMissing,
    BreadthUniverseInvalid,
    analyse,
    available,
    read,
)
from hedge_fund.breadth.store import REFRESH

logger = logging.getLogger(__name__)
router = APIRouter()

#: Sessions of daily series handed to the chart. Twenty-two years of daily
#: points is a quarter of a megabyte that draws as a smear two pixels wide; the
#: episode table and the base rates are computed over the *whole* history
#: regardless, and say so.
CHART_SESSIONS = 756


@router.get("/")
def breadth(
    universe: str = Query("sp500"),
    near: float = Query(2.0, ge=0.0, le=20.0, description="percent below the 252-day high"),
    floor: float = Query(50.0, ge=0.0, le=100.0, description="percent of members above 200dma"),
    sessions: int = Query(CHART_SESSIONS, ge=120, le=6000),
) -> dict[str, Any]:
    try:
        stored = read(universe)
    except BreadthUniverseInvalid as exc:
        # 422, not 503: a malformed name is the caller's mistake, and answering
        # 503 would make a rejected name indistinguishable from a universe that
        # exists but has no cache yet — a file-existence oracle.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BreadthDataMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        result = analyse(stored.breadth, stored.index, near=near, floor=floor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    b = stored.breadth
    tail = slice(-min(sessions, len(b)), None)
    result["series"] = {
        "dates": [str(d.date()) for d in b.dates[tail]],
        "ad_line": _floats(b.ad_line.iloc[tail]),
        "pct_above_200dma": _floats(b.pct_above_200dma.iloc[tail]),
        "net_new_highs_pct": _floats(b.net_new_highs_pct.iloc[tail]),
        "index": _floats(stored.index.reindex(b.dates).iloc[tail]),
    }
    result["source"] = {
        "universe": stored.universe,
        "index_symbol": stored.index_symbol,
        "built_at": stored.built_at.isoformat(),
        "age_days": round(stored.age_days, 2),
        "stale": stored.stale,
        "refresh": REFRESH,
    }
    result["limits"] = LIMITS
    return result


@router.get("/universes")
def universes() -> dict[str, Any]:
    """Which breadth series have been built, and how old each one is."""
    return {"available": available(), "refresh": REFRESH}


def _floats(series: Any) -> list[float | None]:
    return [None if v != v else round(float(v), 4) for v in series]


#: Shown on the screen, not buried in a tooltip. Each one is a reason the
#: number above it could be wrong, in the order a reader would hit them.
LIMITS: list[dict[str, str]] = [
    {
        "title": "Today's members, carried backwards",
        "body": (
            "Breadth is measured across the index's current constituents. Every "
            "company that was in the index and fell out of it — the 2008 banks, the "
            "retailers — is missing from the history, and they are missing because "
            "they fell. Past breadth is therefore flattered, and past divergences "
            "look rarer and milder than they were."
        ),
    },
    {
        "title": "This is not the NYSE advance-decline line",
        "body": (
            "The series the warning is told about counts every issue on the NYSE, "
            "including closed-end funds, rights and preferred stock — largely "
            "interest-rate instruments. This counts the index's own members. The "
            "two can and do diverge from each other."
        ),
    },
    {
        "title": "Twenty-two years, and not the twenty-two that matter",
        "body": (
            "The history starts in 2004. The divergences the warning was built on — "
            "1929, 1962, 1973, 1987 — are outside it, and no free constituent-level "
            "source reaches them. Nothing on this screen tests the original claim."
        ),
    },
    {
        "title": "The sample is episodes, not days",
        "body": (
            "Signal days arrive in clumps and are collapsed into episodes, so the n "
            "beside every median is single or low double digits. A median over six "
            "observations has a confidence interval wide enough to contain almost "
            "any claim, including the opposite one."
        ),
    },
]
