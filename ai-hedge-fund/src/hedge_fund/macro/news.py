"""The committed US growth and inflation news metrics.

One JSON file, built by ``scripts/refresh_macro_news.py`` from FRED, the
Philadelphia Fed's Survey of Professional Forecasters and Kenneth French's
data library. This module only reads it, so nothing here can turn into a
different number between two page loads; the file carries the date it was
built and the UI prints it.

The construction is described in the refresh script and, at source, in AQR's
*Alternative Thinking* 2026 Issue 3. In one line: each metric is the average of
a *change* leg and a *surprise* leg, each divided by its own standard deviation
first, and the average restandardised.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "macro" / "us-macro-news.json"

REFRESH = "uv run --with openpyxl python scripts/refresh_macro_news.py"

#: Ten independent years. Below this the two correlations are a coin toss with
#: decimal places, and the map would be inviting someone to read one.
MIN_QUARTERS = 40

#: Overlapping 12-month windows read off every quarter: four observations per
#: independent year. Dividing by this is crude — it assumes the overlap is the
#: only source of dependence — but it is the difference between claiming 218
#: observations and admitting to about 54.
OVERLAP = 4


class MacroDataMissing(RuntimeError):
    """The committed macro file is absent. Rebuild it with the refresh script."""


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    try:
        loaded: dict[str, Any] = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MacroDataMissing(str(exc)) from exc
    return loaded


def quarters() -> list[str]:
    """The quarter labels every series in the file is aligned to."""
    labels: list[str] = load()["quarters"]
    return labels


def metric(axis: str) -> list[float]:
    """The standardised news metric for ``"inflation"`` or ``"growth"``."""
    data = load()
    if axis not in ("inflation", "growth"):
        raise ValueError(f"no macro axis {axis!r}")
    values: list[float] = data[axis]["news"]
    return values


def context() -> dict[str, Any]:
    """Everything the UI needs to caption the map and draw the news chart."""
    data = load()
    return {
        "built_at": data["built_at"],
        "source": data["source"],
        "quarters": data["quarters"],
        "inflation": data["inflation"],
        "growth": data["growth"],
        "absent": data["absent"],
        "min_quarters": MIN_QUARTERS,
        "overlap": OVERLAP,
    }


def reference_series() -> list[dict[str, Any]]:
    """The anchors and industries, each already a 12-month return per quarter."""
    series: list[dict[str, Any]] = load()["series"]
    return series
