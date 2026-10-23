"""Bullpen.News — hand-curated buy-side commentary, read and summarised.

Bullpen (Dorsey Research) indexes about 130 newsletters, 90 X accounts and 190
fund letters, tags every item by ticker and theme, and writes a one-line
summary. That is the one thing the rest of the data layer cannot supply:
*which serious people are writing about this name, and what kind of story they
think it is.*

Two reads, both public:

- ``/feed.xml`` — the RSS feed, about six days deep. Their terms invite
  subscribing to it. It drives the daily ideas list.
- ``/ticker/<SYM>/__data.json`` — the data behind a ticker page, in SvelteKit's
  flattened format. Not a published API, so it is parsed defensively and a
  shape change returns ``None`` (the registry records the miss) rather than
  half a payload. Fetched one name at a time, on demand, and cached.

What this module does NOT do, on purpose:

- Republish. The terms ask that summaries are not reproduced wholesale, so the
  UI shows titles and sources and links out; summaries go to the analysts'
  prompt only, where they are evidence, not content.
- Score catalysts. A ``special-situations`` tag means someone *wrote* about a
  catalyst, not that one exists. The Bolton screen carries these as leads and
  leaves the judgment to the persona — see ``screeners/bolton_contrarian.py``.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://bullpen.news"
FEED_URL = f"{BASE_URL}/feed.xml"
USER_AGENT = "mario-jude-fund/0.1 (+research; one ticker per request, cached)"
TIMEOUT_S = 15.0

#: Registry key that asks the provider for the RSS feed instead of a ticker.
FEED_KEY = "@feed"

#: Tags that name a Bolton catalyst: something specific about to change the
#: story. Theme tags (AI, Media) and style tags (deep-value) are not catalysts.
CATALYST_TAGS: dict[str, str] = {
    "special-situations": "Special situation",
    "m-a": "M&A",
    "activism": "Activism",
}

#: How far back a written-up catalyst still counts as a live lead.
CATALYST_LOOKBACK_DAYS = 180
#: Windows for the attention counts.
ATTENTION_WINDOWS = (30, 90, 365)
#: Items handed to the analysts and the UI.
RECENT_ITEMS = 6


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------


def _get(url: str) -> httpx.Response:
    return httpx.get(
        url, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    )


def fetch_ticker(ticker: str) -> dict[str, Any] | None:
    """Parsed commentary for one ticker, or None if Bullpen does not cover it."""
    sym = ticker.strip().upper()
    if not sym or "/" in sym:
        return None
    resp = _get(f"{BASE_URL}/ticker/{sym}/__data.json")
    resp.raise_for_status()
    return parse_ticker_payload(resp.json())


def fetch_feed() -> list[dict[str, Any]]:
    resp = _get(FEED_URL)
    resp.raise_for_status()
    return parse_feed(resp.text)


# --------------------------------------------------------------------------
# Parse
# --------------------------------------------------------------------------


def decode_sveltekit(data: list[Any]) -> Any:
    """Rebuild the object graph from SvelteKit's flat ``devalue`` array.

    Every object value and array element is an index into ``data``; index 0 is
    the root. Dates arrive as ``["Date", iso]``. Negative indices are devalue's
    sentinels (undefined, NaN, …) and decode to None.
    """
    memo: dict[int, Any] = {}

    def dec(i: int) -> Any:
        if not isinstance(i, int) or i < 0 or i >= len(data):
            return None
        if i in memo:
            return memo[i]
        v = data[i]
        if isinstance(v, dict):
            out: dict[str, Any] = {}
            memo[i] = out
            out.update({k: dec(j) for k, j in v.items()})
            return out
        if isinstance(v, list):
            if len(v) == 2 and v[0] == "Date" and isinstance(v[1], str):
                return v[1]
            lst: list[Any] = []
            memo[i] = lst
            lst.extend(dec(j) for j in v)
            return lst
        return v

    return dec(0)


def _iso(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).isoformat()
    except ValueError:
        return None


def _out_url(href: Any) -> str | None:
    """Readers go through Bullpen's own redirect, so the click is credited to them."""
    if not isinstance(href, str) or not href.startswith("/"):
        return None
    return BASE_URL + href


def parse_ticker_payload(payload: Any) -> dict[str, Any] | None:
    """Turn a ticker page's ``__data.json`` into the shape the app uses."""
    try:
        nodes = payload["nodes"]
        node = nodes[-1]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(node, dict) or node.get("type") != "data":
        return None  # "error" node: Bullpen does not cover this symbol
    root = decode_sveltekit(node.get("data") or [])
    if not isinstance(root, dict) or not isinstance(root.get("items"), list):
        logger.warning("bullpen: ticker payload changed shape; keys=%s", list(root or {}))
        return None

    company = root.get("company") or {}
    items = []
    for raw in root["items"]:
        if not isinstance(raw, dict) or not raw.get("title"):
            continue
        tags = [t for t in raw.get("tags") or [] if isinstance(t, dict)]
        items.append(
            {
                "id": raw.get("id"),
                "title": str(raw["title"]),
                "summary": raw.get("summary") or None,
                "published_at": _iso(raw.get("publishedAt")),
                "source": raw.get("sourceName") or raw.get("authorName"),
                "source_type": raw.get("sourceType"),
                "url": _out_url(raw.get("href")),
                "tags": [t.get("slug") for t in tags if t.get("slug")],
                "tag_names": [t.get("name") for t in tags if t.get("name")],
                "tickers": [
                    c.get("ticker") for c in raw.get("companies") or [] if isinstance(c, dict)
                ],
            }
        )

    letters = []
    for raw in root.get("letters") or []:
        if not isinstance(raw, dict):
            continue
        letters.append(
            {
                "id": raw.get("id"),
                "firm": raw.get("firmName"),
                "title": raw.get("title"),
                "period": raw.get("periodLabel"),
                # The period end, not publishedAt: Bullpen backfills old letters,
                # so publishedAt is when *they* indexed it. A 1Q22 letter dated
                # 2026 would leak into a 2023 backtest.
                "period_end": raw.get("periodEnd"),
                "summary": raw.get("summary") or None,
                "url": _out_url(raw.get("href")),
            }
        )

    pagination = root.get("pagination") or {}
    return {
        "ticker": company.get("ticker"),
        "company": company.get("name"),
        "market_cap_millions": company.get("marketCapMillions"),
        "total": root.get("total"),
        "has_more": bool(pagination.get("hasNext")),
        "letters_capped": bool(root.get("lettersCapped")),
        "items": items,
        "letters": letters,
        "source": "bullpen.news",
    }


_DC = "{http://purl.org/dc/elements/1.1/}"


def parse_feed(xml_text: str) -> list[dict[str, Any]]:
    """RSS items with their ticker and theme categories split apart."""
    root = ET.fromstring(xml_text)
    out = []
    for item in root.iter("item"):
        tickers, themes = [], []
        for cat in item.findall("category"):
            text = (cat.text or "").strip()
            if not text:
                continue
            (tickers if cat.get("domain") == "ticker" else themes).append(text)
        published = None
        raw_date = item.findtext("pubDate")
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date).astimezone(UTC).isoformat()
            except (TypeError, ValueError):
                published = None
        out.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "url": (item.findtext("link") or "").strip() or None,
                "published_at": published,
                "source": (item.findtext(f"{_DC}creator") or "").strip() or None,
                "tickers": [t.upper() for t in tickers],
                "themes": themes,
            }
        )
    return out


# --------------------------------------------------------------------------
# Summarise
# --------------------------------------------------------------------------

_THEME_SLUG = {name: slug for slug, name in CATALYST_TAGS.items()} | {
    # Feed categories carry display names; Bullpen's own names for the slugs.
    "Special Situations": "special-situations",
    "M&A": "m-a",
    "Activism": "activism",
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def summarize_commentary(
    data: dict[str, Any] | None, *, as_of: date | None = None
) -> dict[str, Any]:
    """Attention counts, catalyst leads and recent items as of a date.

    ``as_of`` drops everything written after it, so a backtest snapshot never
    sees commentary from its own future. Counts are lower bounds when Bullpen
    paginated the history and the oldest item fetched is inside the window —
    the ``complete`` flag on each window says which.
    """
    if not data:
        return {"covered": False, "source": "bullpen.news"}

    now = datetime.combine(as_of, datetime.max.time(), tzinfo=UTC) if as_of else datetime.now(UTC)
    items = [
        (dt, it)
        for it in data.get("items") or []
        if (dt := _parse_dt(it.get("published_at"))) is not None and dt <= now
    ]
    items.sort(key=lambda p: p[0], reverse=True)
    oldest = items[-1][0] if items else None
    # Items were cut by pagination only if Bullpen had more than it sent.
    truncated = bool(data.get("has_more"))

    # A backtest dated before everything fetched cannot see its own window at
    # all. Zero there would read as "neglected"; the truth is "not fetched".
    blind = truncated and not items

    def window(days: int) -> dict[str, Any]:
        start = now - timedelta(days=days)
        inside = [it for dt, it in items if dt >= start]
        complete = not truncated or (oldest is not None and oldest < start)
        return {
            "days": days,
            "items": None if blind else len(inside),
            "sources": None
            if blind
            else len({it.get("source") for it in inside if it.get("source")}),
            # False: Bullpen has older items than were fetched, so the count is a floor.
            "complete": complete,
        }

    as_of_day = now.date()
    letters = [
        lt
        for lt in data.get("letters") or []
        if not lt.get("period_end") or str(lt["period_end"])[:10] <= as_of_day.isoformat()
    ]
    letters.sort(key=lambda lt: str(lt.get("period_end") or ""), reverse=True)

    lead_start = now - timedelta(days=CATALYST_LOOKBACK_DAYS)
    leads = []
    for dt, it in items:
        if dt < lead_start:
            break
        kinds = [CATALYST_TAGS[t] for t in it.get("tags") or [] if t in CATALYST_TAGS]
        if kinds:
            leads.append(_public_item(it) | {"catalyst": kinds})

    windows = {f"{w}d": window(w) for w in ATTENTION_WINDOWS}
    return {
        "covered": True,
        "source": "bullpen.news",
        "as_of": as_of_day.isoformat(),
        "company": data.get("company"),
        "all_time_items": data.get("total"),
        "attention": windows,
        "letters": {
            "count": len(letters),
            "capped": bool(data.get("letters_capped")),
            "recent": [
                {k: lt.get(k) for k in ("firm", "period", "period_end", "url", "summary")}
                for lt in letters[:3]
            ],
        },
        "catalyst_leads": leads,
        "recent": [_public_item(it) for _, it in items[:RECENT_ITEMS]],
    }


def _public_item(it: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": it.get("title"),
        "summary": it.get("summary"),
        "published_at": it.get("published_at"),
        "source": it.get("source"),
        "source_type": it.get("source_type"),
        "url": it.get("url"),
        "tags": it.get("tag_names") or [],
    }


def ideas_from_feed(
    feed: list[dict[str, Any]], *, known: set[str] | None = None
) -> list[dict[str, Any]]:
    """Group the feed by ticker: who wrote about it, and is it a catalyst story.

    ``known`` is every symbol in the app's universes; a name outside them is
    flagged ``new`` because it is the one the existing screens never saw.
    """
    by_ticker: dict[str, dict[str, Any]] = {}
    for item in feed:
        kinds = sorted(
            {CATALYST_TAGS[s] for t in item.get("themes") or [] if (s := _THEME_SLUG.get(t))}
        )
        for sym in item.get("tickers") or []:
            row = by_ticker.setdefault(
                sym,
                {"ticker": sym, "mentions": 0, "sources": set(), "catalyst": set(), "items": []},
            )
            row["mentions"] += 1
            if item.get("source"):
                row["sources"].add(item["source"])
            row["catalyst"].update(kinds)
            row["items"].append(
                {k: item.get(k) for k in ("title", "url", "published_at", "source")}
            )

    out = []
    for row in by_ticker.values():
        row["sources"] = sorted(row["sources"])
        row["catalyst"] = sorted(row["catalyst"])
        row["in_universe"] = None if known is None else row["ticker"] in known
        out.append(row)
    # Catalyst stories first, then breadth of independent sources.
    out.sort(key=lambda r: (-len(r["catalyst"]), -len(r["sources"]), -r["mentions"], r["ticker"]))
    return out


def commentary_for_model(commentary: dict[str, Any]) -> dict[str, Any]:
    """The analysts' view of buy-side commentary: opinions, labelled as such.

    Links and display fields are dropped; summaries stay, because they are the
    evidence. The note travels with the data so a model that only sees this
    section still knows it is reading other investors, not facts.
    """
    if commentary.get("unavailable"):
        return {"covered": None, "note": "Commentary could not be fetched; treat as unknown."}
    if not commentary.get("covered"):
        return {"covered": False, "note": "No curated buy-side commentary on this name."}

    def item(it: dict[str, Any]) -> dict[str, Any]:
        out = {k: it.get(k) for k in ("published_at", "source", "title", "summary", "tags")}
        if it.get("catalyst"):
            out["catalyst"] = it["catalyst"]
        return out

    return {
        "covered": True,
        "note": (
            "Other investors' published opinions, curated by Bullpen.News. Weigh them as "
            "views, not facts: cite them as '<source> argues', never use their numbers "
            "as data. Attention counts measure how much serious coverage the name gets; "
            "complete=false means the count is a floor."
        ),
        "attention": commentary.get("attention"),
        "fund_letters_mentioning": commentary.get("letters", {}).get("count"),
        "fund_letters_recent": [
            {k: lt.get(k) for k in ("firm", "period", "summary")}
            for lt in commentary.get("letters", {}).get("recent", [])
        ],
        "catalyst_leads": [item(it) for it in commentary.get("catalyst_leads", [])[:4]],
        "recent": [item(it) for it in commentary.get("recent", [])],
    }
