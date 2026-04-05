"""
Liquid index / exchange universes for screeners (ticker lists).

Sources: public CSVs (S&P 500), Wikipedia tables (NASDAQ-100, Dow 30),
iShares IWM holdings CSV (Russell 2000 proxy). Symbols normalized for Yahoo Finance.
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
        "id": "nasdaq100",
        "label": "NASDAQ-100",
        "description": "NASDAQ-100 index (Wikipedia). Not the full NASDAQ Composite.",
        "approx_count": 100,
    },
    {
        "id": "dow",
        "label": "Dow Jones 30",
        "description": "Dow Jones Industrial Average (Wikipedia).",
        "approx_count": 30,
    },
    {
        "id": "russell2000",
        "label": "Russell 2000 (IWM)",
        "description": "iShares Russell 2000 ETF holdings — practical proxy for the small-cap index (~2k names).",
        "approx_count": 2000,
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


def fetch_nasdaq100() -> list[str]:
    html = _fetch_url_text("https://en.wikipedia.org/wiki/Nasdaq-100")
    tables = pd.read_html(io.StringIO(html))
    for t in tables:
        if "Ticker" in t.columns:
            syms = [normalize_yahoo_symbol(x) for x in t["Ticker"].tolist() if pd.notna(x)]
            # Dedupe while preserving order
            seen: set[str] = set()
            out: list[str] = []
            for s in syms:
                if s not in seen:
                    seen.add(s)
                    out.append(s)
            return out
    raise ValueError("Could not parse NASDAQ-100 table from Wikipedia")


def fetch_dow() -> list[str]:
    html = _fetch_url_text("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average")
    tables = pd.read_html(io.StringIO(html))
    for t in tables:
        if "Symbol" in t.columns and len(t) >= 25:
            return [normalize_yahoo_symbol(x) for x in t["Symbol"].tolist() if pd.notna(x)]
    raise ValueError("Could not parse Dow 30 table from Wikipedia")


def fetch_russell2000_iwm() -> list[str]:
    """Russell 2000 via iShares IWM holdings CSV (full replication, ~2k lines)."""

    url = (
        "https://www.ishares.com/us/products/239710/"
        "ishares-russell-2000-etf/1467271812596.ajax"
        "?fileType=csv&fileName=IWM_holdings&dataType=fund"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _WIKI_UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode("utf-8", errors="replace")
    # Skip preamble until header row
    lines = raw.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if line.startswith("Ticker,") or line.startswith('"Ticker"'):
            start = i
            break
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    col = "Ticker" if "Ticker" in df.columns else None
    if col is None:
        raise ValueError("IWM CSV missing Ticker column")
    syms = [normalize_yahoo_symbol(x) for x in df[col].tolist() if pd.notna(x) and str(x).strip()]
    seen: set[str] = set()
    out: list[str] = []
    for s in syms:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def load_universe(universe_id: str) -> list[str]:
    uid = universe_id.strip().lower()
    loaders = {
        "sp500": lambda: _cached("sp500", fetch_sp500),
        "nasdaq100": lambda: _cached("nasdaq100", fetch_nasdaq100),
        "dow": lambda: _cached("dow", fetch_dow),
        "russell2000": lambda: _cached("russell2000", fetch_russell2000_iwm),
    }
    if uid not in loaders:
        raise ValueError(f"unknown universe: {universe_id!r}")
    return loaders[uid]()


def list_universe_meta() -> list[dict[str, Any]]:
    return list(UNIVERSE_META)
