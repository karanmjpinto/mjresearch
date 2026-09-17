"""
Liquid index universes for screeners (ticker lists).

The three S&P size bands, which between them cover most of the investable US
market: 500 large caps, 400 mid, 600 small. Symbols normalised for Yahoo.

Four sources were tried and three of them are gone, which is worth recording
so the next person does not rebuild them:

  NASDAQ-100, Dow 30   Wikipedia stopped rendering the constituent tables into
                       the article HTML; `read_html` now finds only navboxes
                       and the price-history tables on both pages.
  Russell 2000 (IWM)   iShares serves an HTML page from the holdings-CSV
                       endpoint, so the parse got a web page, not a fund.

A loader that always raises is worse than an absent one — it puts a choice in
the UI that can only fail — so they are not listed. The S&P 600 replaces the
Russell 2000 as the small-cap universe: a real index rather than one fund's
holdings, and the band the multi-bagger screen actually needs.
"""

from __future__ import annotations

import io
import logging
import time
import urllib.request
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_WIKI_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# (id, label, description, approx_count for UI)
UNIVERSE_META: list[dict[str, Any]] = [
    {
        "id": "sp500",
        "label": "S&P 500",
        "description": "S&P 500 constituents (datasets.org CSV, updated periodically).",
        "approx_count": 503,
    },
    {
        "id": "sp400",
        "label": "S&P MidCap 400",
        "description": "Mid-caps, roughly $7bn to $20bn. Below the 500, above the 600.",
        "approx_count": 400,
    },
    {
        "id": "sp600",
        "label": "S&P SmallCap 600",
        "description": (
            "Small-caps, roughly $1bn to $7bn — where a company can still "
            "multiply several times over. The universe the multi-bagger screen "
            "is built for; it can pass nothing in the S&P 500."
        ),
        "approx_count": 600,
    },
]

_CACHE: dict[str, tuple[float, list[str]]] = {}
_TTL_SEC = 86_400  # 24h — constituents change slowly


def normalize_yahoo_symbol(sym: str) -> str:
    s = str(sym).strip().upper()
    return s.replace(".", "-")


def _cached(key: str, loader: Any) -> list[str]:
    now = time.time()
    if key in _CACHE:
        ts, data = _CACHE[key]
        if now - ts < _TTL_SEC:
            return data
    data = loader()
    _CACHE[key] = (now, data)
    return data


def _fetch_url_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _WIKI_UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_sp500() -> list[str]:
    """S&P 500 from datasets GitHub (reliable, no Wikipedia)."""

    url = (
        "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
        "master/data/constituents.csv"
    )
    df = pd.read_csv(url)
    if "Symbol" not in df.columns:
        raise ValueError("S&P 500 CSV missing Symbol column")
    return [normalize_yahoo_symbol(x) for x in df["Symbol"].tolist() if pd.notna(x)]


def _fetch_sp_list(page: str, expected: int) -> list[str]:
    """Constituents from a Wikipedia "List of S&P N companies" article.

    These list articles still render a real constituents table into the page
    HTML, unlike the index articles. The table is picked by shape rather than
    position — the first one carrying a Symbol column and roughly the expected
    number of rows — so a new table appearing above it does not silently
    return a changelog of additions and removals instead of the index.
    """
    tables = pd.read_html(io.StringIO(_fetch_url_text(page)))
    for t in tables:
        cols = [str(c) for c in t.columns]
        if "Symbol" in cols and len(t) >= expected * 0.8:
            syms = [normalize_yahoo_symbol(x) for x in t["Symbol"].tolist() if pd.notna(x)]
            return _dedupe(syms)
    raise ValueError(f"could not find a constituents table at {page}")


def _dedupe(syms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in syms:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def fetch_sp400() -> list[str]:
    return _fetch_sp_list("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", 400)


def fetch_sp600() -> list[str]:
    return _fetch_sp_list("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies", 600)


#: Module-level rather than built inside `load_universe`, so that the one
#: invariant that actually broke here is testable: every universe advertised in
#: UNIVERSE_META must have a loader, and every loader must be advertised. The
#: UI builds its dropdown from the metadata, so a listed universe with no
#: working loader is a choice that can only fail — which is exactly what the
#: NASDAQ-100, Dow and Russell 2000 entries were for months.
LOADERS: dict[str, Any] = {
    "sp500": fetch_sp500,
    "sp400": fetch_sp400,
    "sp600": fetch_sp600,
}


def load_universe(universe_id: str) -> list[str]:
    uid = universe_id.strip().lower()
    if uid not in LOADERS:
        raise ValueError(f"unknown universe: {universe_id!r}")
    return _cached(uid, LOADERS[uid])


def list_universe_meta() -> list[dict[str, Any]]:
    return list(UNIVERSE_META)
