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

Japan is the exception to the scraping pattern, because it had to be. The
Kiyohara screen reads the Japan Company Handbook's own checks, so it needs a
Japanese universe, and the obvious sources are the ones already known to be
dead: the Nikkei 225 Wikipedia article renders no constituents table and its
navbox is lazy-loaded, so `read_html` finds price history and nothing else.
The Tokyo exchange publishes the list itself — every domestic listing with its
33-sector code and its TOPIX size band — so `jp_mid_small` comes from the
primary source rather than a third party's rendering of it.
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
    {
        "id": "jp_mid_small",
        "label": "Japan mid & small",
        "description": (
            "TOPIX Mid400 plus Small 1 — the mid and small Japanese companies "
            "the Kiyohara screen is written for. Sourced from the Tokyo "
            "exchange's own listing file."
        ),
        "approx_count": 874,
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
    return _fetch_url_bytes(url).decode("utf-8", errors="replace")


def _fetch_url_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _WIKI_UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return bytes(r.read())


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


#: Every domestic listing on the Tokyo exchange, with its sector and its
#: TOPIX size band. Published by JPX in English and updated monthly.
JPX_LISTED_URL = (
    "https://www.jpx.co.jp/english/markets/statistics-equities/misc/"
    "tvdivq0000001vg2-att/data_e.xlsx"
)

#: The size bands the Kiyohara screen wants. He ran a Japanese small and mid
#: cap fund, and the two largest bands — Core30 and Large70 — are the hundred
#: companies every Japanese institution already owns, which is the opposite of
#: the shelf he worked off. TOPIX Small 2 is left out for length rather than
#: principle: it is another 660 names, and each one costs a few seconds of
#: waiting on the data provider.
JP_MID_SMALL_BANDS = ("TOPIX Mid400", "TOPIX Small 1")


def jp_symbol(code: str) -> str:
    """A Tokyo listing code as Yahoo spells it: `7203` becomes `7203.T`.

    Deliberately not `normalize_yahoo_symbol`, which turns a dot into a hyphen
    for US class shares and would make `7203.T` into `7203-T` — a symbol that
    returns no data rather than an error. Codes are left-padded because the
    exchange file stores them as text but a spreadsheet round-trip can drop a
    leading zero, and some are alphanumeric now (`160A`), so this does not
    assume digits.
    """
    c = str(code).strip().upper()
    if c.isdigit():
        c = c.zfill(4)
    return f"{c}.T"


def fetch_jp_mid_small() -> list[str]:
    """Mid and small Japanese companies, from the exchange's own listing file.

    Picked by the two columns that matter rather than by row position, for the
    same reason the S&P loaders pick their table by shape: the file carries
    ETFs, REITs, foreign listings and the PRO market alongside the domestic
    companies, and taking it whole would put 485 exchange-traded funds into a
    screen that reads company balance sheets.
    """
    raw = _fetch_url_bytes(JPX_LISTED_URL)
    df = pd.read_excel(io.BytesIO(raw))

    needed = {"Local Code", "Section/Products", "Size (New Index Series)"}
    missing = needed - {str(c) for c in df.columns}
    if missing:
        raise ValueError(f"JPX listing file is missing columns: {sorted(missing)}")

    domestic = df["Section/Products"].astype(str).str.contains("Domestic", na=False)
    banded = df["Size (New Index Series)"].astype(str).str.strip().isin(JP_MID_SMALL_BANDS)
    rows = df[domestic & banded]

    # A shrunken file is the failure this guards. If JPX changes the size
    # labels, the filter matches nothing and returns an empty universe — which
    # reads downstream as a market with no companies in it rather than as a
    # broken loader.
    if len(rows) < 600:
        raise ValueError(
            f"JPX listing file yielded only {len(rows)} mid/small names "
            f"(expected ~874) — the size bands {JP_MID_SMALL_BANDS} may have been renamed"
        )
    return _dedupe([jp_symbol(c) for c in rows["Local Code"].tolist() if pd.notna(c)])


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
    "jp_mid_small": fetch_jp_mid_small,
}


def load_universe(universe_id: str) -> list[str]:
    uid = universe_id.strip().lower()
    if uid not in LOADERS:
        raise ValueError(f"unknown universe: {universe_id!r}")
    return _cached(uid, LOADERS[uid])


def list_universe_meta() -> list[dict[str, Any]]:
    return list(UNIVERSE_META)
