"""The built breadth series on disk, with the date it was built.

Same bargain as :mod:`hedge_fund.screeners.cache`, for the same reason: the
expensive half of this screen is five hundred price histories, which is half a
minute of waiting on a public endpoint and cannot sit in a request. So it is
built ahead of time and served instantly, dated.

What is *not* precomputed is the analysis. The divergence thresholds are a
control in the UI — the whole point being that a reader can see how much the
answer depends on where the line is drawn — so the stored artifact is the raw
daily series and :func:`hedge_fund.breadth.divergence.analyse` runs per request
over a few thousand rows, which costs milliseconds.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from pathlib import Path
from typing import Any

import pandas as pd

from hedge_fund.breadth.series import Breadth

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "breadth"

#: How to rebuild, quoted verbatim to the reader when the file is missing. A
#: 503 that says "data is not available" and nothing else is a dead end.
REFRESH = "uv run python scripts/refresh_breadth.py"

#: Past this the API says so. Breadth moves daily, so unlike the quarterly
#: screens a fortnight-old file is not merely dated, it is answering about a
#: different market.
STALE_DAYS = 3


class BreadthDataMissing(RuntimeError):
    """No built series for this universe."""


@dataclass(frozen=True)
class StoredBreadth:
    universe: str
    built_at: datetime
    breadth: Breadth
    index: pd.Series
    index_symbol: str

    @property
    def age_days(self) -> float:
        return (datetime.now(UTC) - self.built_at).total_seconds() / 86400

    @property
    def stale(self) -> bool:
        return self.age_days > STALE_DAYS


#: A universe name is a filename component, so it is constrained to one.
#: `universe` arrives from a query string (`GET /api/breadth/?universe=...`) and
#: is interpolated into a path, which without this is a directory traversal:
#: `../../../../etc/foo` escapes the cache directory and turns the endpoint into
#: a reader for any .json the process can open. Validated here, at the lowest
#: layer, rather than at the route — every caller gets the check, including the
#: writer and any future one.
_UNIVERSE = re.compile(r"^[a-z0-9_-]{1,32}$")


class BreadthUniverseInvalid(ValueError):
    """The universe name is not a name. Raised before any filesystem access."""


def _path(universe: str) -> Path:
    if not _UNIVERSE.match(universe or ""):
        raise BreadthUniverseInvalid(
            f"{universe!r} is not a universe name: expected lowercase letters, "
            "digits, hyphen or underscore, up to 32 characters."
        )
    resolved = (CACHE_DIR / f"{universe}.json").resolve()
    # Belt and braces. The pattern above already forbids separators and dots,
    # so this can only fire if that pattern is ever loosened.
    if not resolved.is_relative_to(CACHE_DIR.resolve()):
        raise BreadthUniverseInvalid(f"{universe!r} escapes the cache directory.")
    return resolved


def write(
    universe: str,
    breadth: Breadth,
    index: pd.Series,
    *,
    index_symbol: str,
    members_requested: int,
    members_fetched: int,
) -> Path:
    """Replace the stored series, atomically.

    Written to a temporary file in the same directory and renamed, so a run
    killed halfway leaves the previous build in place rather than a truncated
    JSON file that every later request fails to parse.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    aligned = index.reindex(breadth.dates)
    payload = {
        "universe": universe,
        "built_at": datetime.now(UTC).isoformat(),
        "index_symbol": index_symbol,
        "members_requested": members_requested,
        "members_fetched": members_fetched,
        "dates": [str(d.date()) for d in breadth.dates],
        "ad_line": [_f(v) for v in breadth.ad_line],
        "pct_above_200dma": [_f(v) for v in breadth.pct_above_200dma],
        "net_new_highs_pct": [_f(v) for v in breadth.net_new_highs_pct],
        "members": [int(v) for v in breadth.members],
        "index": [_f(v) for v in aligned],
    }

    fd, tmp = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
        os.replace(tmp, _path(universe))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return _path(universe)


def _f(value: Any) -> float | None:
    """A JSON-safe float. NaN is `null`, not the string `NaN`.

    `json.dump` writes a bare `NaN` token by default, which is not JSON and
    which every strict parser on the other end rejects.
    """
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(out) else round(out, 4)


def read(universe: str) -> StoredBreadth:
    """Load the stored series, or say how to build it."""
    path = _path(universe)
    if not path.is_file():
        raise BreadthDataMissing(
            f"no breadth series has been built for {universe!r}. Build it with: {REFRESH}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        dates = pd.DatetimeIndex(pd.to_datetime(payload["dates"]))
        series = {
            key: pd.Series(payload[key], index=dates, dtype="float64")
            for key in ("ad_line", "pct_above_200dma", "net_new_highs_pct", "members", "index")
        }
    except (OSError, ValueError, KeyError) as exc:
        raise BreadthDataMissing(
            f"the breadth series for {universe!r} could not be read ({exc}). Rebuild it with: {REFRESH}"
        ) from exc

    return StoredBreadth(
        universe=payload["universe"],
        built_at=datetime.fromisoformat(payload["built_at"]),
        breadth=Breadth(
            dates=dates,
            ad_line=series["ad_line"],
            pct_above_200dma=series["pct_above_200dma"],
            net_new_highs_pct=series["net_new_highs_pct"],
            members=series["members"],
        ),
        index=series["index"],
        index_symbol=payload.get("index_symbol", "^GSPC"),
    )


def available() -> list[dict[str, Any]]:
    """Every built universe, with its age. Used by the API to list choices."""
    out = []
    for path in sorted(CACHE_DIR.glob("*.json")) if CACHE_DIR.is_dir() else []:
        try:
            stored = read(path.stem)
        except BreadthDataMissing:
            continue
        out.append(
            {
                "universe": stored.universe,
                "built_at": stored.built_at.isoformat(),
                "age_days": round(stored.age_days, 2),
                "stale": stored.stale,
            }
        )
    return out
