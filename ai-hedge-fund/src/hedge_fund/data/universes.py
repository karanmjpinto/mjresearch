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

Four more regions were added for the same reason Japan was: a desk looking for
quality small and mid caps *across the globe* cannot do it from three American
size bands. Each one was probed before it was written, and the ones that only
looked like sources were left out:

  au_all   ASX publishes every listed company as a CSV. Primary, 1.9k rows.
  ca_all   The Toronto exchange publishes its company directory as JSON.
           Primary, but 2.3k rows of which roughly two thirds are ETFs,
           bond trusts, split corps and preferred series — see `fetch_ca_all`.
  uk_mid   FTSE 250 from Wikipedia's list article, which still renders a real
           constituents table carrying a Ticker column.
  de_mid   MDAX, likewise, carrying a Symbol column of Xetra tickers.

And the three that were rejected, so nobody rebuilds them:

  SDAX (DE small)    The article's table has Logo, Name, Industry, Location
                     and no ticker column at all. The names are there and the
                     symbols are not, which is not a universe.
  STOXX Europe 600   The table renders 467 of 600 constituents. A loader that
                     returns 78% of an index and says nothing is worse than
                     one that fails: every absent company reads as "screened
                     and did not qualify".
  Nifty Midcap 150   niftyindices.com answers the constituent CSV with HTTP
                     403. Deferred rather than routed around, because the
                     obvious workarounds are third-party re-publications of
                     exactly the kind that killed the Russell 2000 loader.
"""

from __future__ import annotations

import io
import json
import logging
import re
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
    {
        "id": "uk_mid",
        "label": "UK mid (FTSE 250)",
        "description": (
            "The 250 companies below the FTSE 100 — the British mid-cap band, "
            "and the one a London quality investor actually fishes in."
        ),
        "approx_count": 250,
    },
    {
        "id": "de_mid",
        "label": "Germany mid (MDAX)",
        "description": (
            "The 50 German mid caps below the DAX. Small by index count, but "
            "this is where the Mittelstand niche leaders are listed."
        ),
        "approx_count": 50,
    },
    {
        "id": "ca_all",
        "label": "Canada (TSX operating cos)",
        "description": (
            "Toronto-listed operating companies, from the exchange's own "
            "directory with the funds, trusts and preferred series removed. "
            "Not a size band — the screen's own cap filter does that."
        ),
        "approx_count": 800,
    },
    {
        "id": "au_all",
        "label": "Australia (ASX listed)",
        "description": (
            "Every ASX-listed company, from the exchange's own CSV. Mostly "
            "small and mid by nature. The largest universe here, so a full "
            "run is the slowest — expect to wait on the data provider."
        ),
        "approx_count": 1900,
    },
]

_CACHE: dict[str, tuple[float, list[str]]] = {}
_TTL_SEC = 86_400  # 24h — constituents change slowly


def normalize_yahoo_symbol(sym: str) -> str:
    s = str(sym).strip().upper()
    return s.replace(".", "-")


def exchange_symbol(sym: str, suffix: str = "") -> str:
    """A local ticker as Yahoo spells it on a non-US exchange.

    The order of the two operations is the whole point, and getting it wrong
    is silent. Yahoo wants a hyphen where the exchange writes a dot for a
    share class, and a dot before the exchange code: Rogers class B is `RCI.B`
    in Toronto and `RCI-B.TO` at Yahoo. Appending the suffix first and then
    normalising gives `RCI-B-TO`, which is not an error — it is a symbol that
    returns no data, so the company reads downstream as one with no financials
    rather than one with a mistyped ticker.

    This is the same trap `jp_symbol` documents for `7203.T`. That function
    stays separate because Tokyo codes are numeric and need zero-padding,
    which no other exchange here does.
    """
    base = normalize_yahoo_symbol(sym)
    if not base:
        return ""
    return f"{base}{suffix}"


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


def _fetch_wiki_list(page: str, column: str, expected: int, suffix: str = "") -> list[str]:
    """Constituents from a Wikipedia article that renders a real ticker table.

    The table is picked by shape rather than position — the first one carrying
    the named ticker column and roughly the expected number of rows — so a new
    table appearing above it does not silently return a changelog of additions
    and removals instead of the index.

    `column` is a parameter because the articles disagree: the S&P lists call
    it "Symbol", the FTSE 250 calls it "Ticker", and MDAX calls it "Symbol"
    but puts it last. Hardcoding one spelling is what made this S&P-only.
    """
    tables = pd.read_html(io.StringIO(_fetch_url_text(page)))
    for t in tables:
        cols = [str(c) for c in t.columns]
        if column in cols and len(t) >= expected * 0.8:
            syms = [exchange_symbol(x, suffix) for x in t[column].tolist() if pd.notna(x)]
            return _dedupe([s for s in syms if s])
    raise ValueError(f"could not find a constituents table at {page}")


def _fetch_sp_list(page: str, expected: int) -> list[str]:
    """The S&P spelling of the above: a "Symbol" column and no suffix."""
    return _fetch_wiki_list(page, "Symbol", expected)


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


#: The FTSE 250 and MDAX list articles. Both still render a constituents
#: table with a ticker column, unlike the index articles the dead loaders
#: pointed at. Checked against the live pages before being added.
FTSE250_URL = "https://en.wikipedia.org/wiki/FTSE_250_Index"
MDAX_URL = "https://en.wikipedia.org/wiki/MDAX"


def fetch_uk_mid() -> list[str]:
    """FTSE 250 constituents, suffixed for London."""
    return _fetch_wiki_list(FTSE250_URL, "Ticker", 250, ".L")


def fetch_de_mid() -> list[str]:
    """MDAX constituents, suffixed for Xetra.

    The expected count is 50 and the table renders 52, because Wikipedia
    carries a couple of rows for companies in the middle of index changes.
    The shape check tolerates that; it is there to catch a stub, not to
    audit index membership to the name.
    """
    return _fetch_wiki_list(MDAX_URL, "Symbol", 50, ".DE")


#: Every company listed on the ASX, published by the exchange as a CSV with
#: one banner line above the header.
ASX_LISTED_URL = "https://www.asx.com.au/asx/research/ASXListedCompanies.csv"


def fetch_au_all() -> list[str]:
    """Australian listed companies, from the exchange's own CSV."""
    raw = _fetch_url_bytes(ASX_LISTED_URL).decode("utf-8", errors="replace")
    df = pd.read_csv(io.StringIO(raw), skiprows=1)

    col = "ASX code"
    if col not in {str(c) for c in df.columns}:
        raise ValueError(f"ASX listing CSV is missing the {col!r} column: {list(df.columns)}")

    syms = [exchange_symbol(c, ".AX") for c in df[col].tolist() if pd.notna(c)]
    out = _dedupe([s for s in syms if s])

    # Same guard as the Japan loader, for the same reason: a banner-only or
    # truncated file would otherwise become "the Australian market".
    if len(out) < 1_000:
        raise ValueError(
            f"ASX listing CSV yielded only {len(out)} companies (expected ~1900) "
            "— the file layout or the skipped banner line may have changed"
        )
    return out


#: The Toronto exchange's own company directory. `^*` is its wildcard for
#: "every letter", which is how the site's own A-Z page is populated.
TSX_DIRECTORY_URL = "https://www.tsx.com/json/company-directory/search/tsx/%5E*"

#: Series suffixes that mark something other than a common share: units,
#: preferreds, debentures, warrants, rights, notes, instalment receipts.
#: Class shares (`.A`, `.B`) are deliberately absent — those are companies.
_TSX_NON_COMMON = re.compile(r"\.(UN|PR|DB|WT|RT|NT|NS|IR)[A-Z]?$")

#: And the ones a suffix does not catch, because an ETF can hold a plain
#: four-letter symbol. Matched on the issuer's own name.
_TSX_NOT_A_COMPANY = re.compile(
    r"\b(ETF|Trust|Fund|Index|Bond|Income Securities|Split Corp|Depositary|Preferred)\b",
    re.IGNORECASE,
)


def fetch_ca_all() -> list[str]:
    """Toronto-listed operating companies, with the fund complex removed.

    The directory is primary and complete, which is the problem: 2,305 rows,
    of which roughly 1,500 are ETFs, bond trusts, split corps and preferred
    series. Taking it whole would put a quality screen that reads ROIC and
    FCF conversion over a list that is mostly closed-end funds — the same
    mistake the JPX loader avoids by filtering on section.

    Toronto has no section column, so this filters on two signals instead: a
    series suffix that cannot belong to a common share, and an issuer name
    that says what it is. Both are needed; neither alone is enough.
    """
    payload = json.loads(_fetch_url_bytes(TSX_DIRECTORY_URL))
    rows = payload.get("results") or []
    if not rows:
        raise ValueError("TSX company directory returned no results")

    out: list[str] = []
    for row in rows:
        sym = str(row.get("symbol") or "").strip().upper()
        name = str(row.get("name") or "")
        if not sym or _TSX_NON_COMMON.search(sym) or _TSX_NOT_A_COMPANY.search(name):
            continue
        out.append(exchange_symbol(sym, ".TO"))

    out = _dedupe([s for s in out if s])
    if len(out) < 400:
        raise ValueError(
            f"TSX directory yielded only {len(out)} operating companies (expected ~800) "
            "— the directory shape or the exclusion patterns may need revisiting"
        )
    return out


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
    "uk_mid": fetch_uk_mid,
    "de_mid": fetch_de_mid,
    "ca_all": fetch_ca_all,
    "au_all": fetch_au_all,
}


def load_universe(universe_id: str) -> list[str]:
    uid = universe_id.strip().lower()
    if uid not in LOADERS:
        raise ValueError(f"unknown universe: {universe_id!r}")
    return _cached(uid, LOADERS[uid])


def list_universe_meta() -> list[dict[str, Any]]:
    return list(UNIVERSE_META)
