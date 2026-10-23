"""Bullpen.News commentary: parsing, the as-of cut, and what the screen may do with it.

Payloads are synthetic but in Bullpen's real shapes (SvelteKit's flattened
``devalue`` array; RSS with ticker-domain categories), so a format change on
their side shows up as a parse returning None, which these tests pin.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from hedge_fund.data import bullpen as bp
from hedge_fund.screeners.bolton_contrarian import BoltonResult, attach_catalyst_leads


def _flatten(root: object) -> list[object]:
    """Encode a value the way SvelteKit does: every child is an index."""
    out: list[object] = []

    def enc(v: object) -> int:
        i = len(out)
        out.append(None)
        if isinstance(v, dict):
            out[i] = {k: enc(x) for k, x in v.items()}
        elif isinstance(v, list):
            out[i] = [enc(x) for x in v]
        else:
            out[i] = v
        return i

    enc(root)
    return out


def _item(i: int, when: str, tags: tuple[str, ...] = (), source: str = "Writer A") -> dict:
    return {
        "id": i,
        "title": f"Item {i}",
        "summary": f"Summary {i}",
        "publishedAt": when,
        "sourceName": source,
        "sourceType": "substack",
        "href": f"/out/{i}",
        "tags": [{"slug": t, "name": t.title()} for t in tags],
        "companies": [{"ticker": "KSS"}],
    }


def _payload(items: list[dict], *, has_next: bool = False, letters: list | None = None) -> dict:
    root = {
        "company": {"ticker": "KSS", "name": "Kohl's"},
        "items": items,
        "total": len(items) + (10 if has_next else 0),
        "pagination": {"hasNext": has_next},
        "letters": letters or [],
        "lettersCapped": False,
    }
    return {
        "type": "data",
        "nodes": [{"type": "data", "data": []}, {"type": "data", "data": _flatten(root)}],
    }


def test_decode_handles_dates_and_shared_references():
    data = [{"a": 1, "b": 2, "c": 2}, ["Date", "2026-10-01T00:00:00.000Z"], [3], "x"]
    out = bp.decode_sveltekit(data)
    assert out == {"a": "2026-10-01T00:00:00.000Z", "b": ["x"], "c": ["x"]}


def test_uncovered_ticker_is_none_not_empty():
    payload = {"type": "data", "nodes": [{"type": "data"}, {"type": "error", "status": 404}]}
    assert bp.parse_ticker_payload(payload) is None
    assert bp.summarize_commentary(None) == {"covered": False, "source": "bullpen.news"}


def test_shape_change_returns_none():
    payload = {"nodes": [{}, {"type": "data", "data": _flatten({"stories": []})}]}
    assert bp.parse_ticker_payload(payload) is None


def test_windows_leads_and_links():
    data = bp.parse_ticker_payload(
        _payload(
            [
                _item(1, "2026-10-20T00:00:00.000Z", ("m-a",), "Writer A"),
                _item(2, "2026-09-01T00:00:00.000Z", ("retail",), "Writer B"),
                _item(3, "2025-01-01T00:00:00.000Z", ("special-situations",), "Writer A"),
            ]
        )
    )
    s = bp.summarize_commentary(data, as_of=date(2026, 10, 21))
    assert s["attention"]["30d"] == {"days": 30, "items": 1, "sources": 1, "complete": True}
    assert s["attention"]["90d"]["items"] == 2
    assert s["attention"]["90d"]["sources"] == 2
    # Only the recent M&A item is a lead; the 2025 special situation is stale.
    assert [lead["title"] for lead in s["catalyst_leads"]] == ["Item 1"]
    assert s["catalyst_leads"][0]["catalyst"] == ["M&A"]
    assert s["recent"][0]["url"] == "https://bullpen.news/out/1"


def test_as_of_never_sees_the_future():
    data = bp.parse_ticker_payload(
        _payload(
            [_item(1, "2026-10-20T00:00:00.000Z", ("m-a",)), _item(2, "2026-01-10T00:00:00.000Z")],
            letters=[
                {
                    "firmName": "Old",
                    "periodLabel": "1Q22",
                    "periodEnd": "2022-03-31",
                    "publishedAt": "2026-08-29T00:00:00.000Z",
                },
                {"firmName": "New", "periodLabel": "3Q26", "periodEnd": "2026-09-30"},
            ],
        )
    )
    s = bp.summarize_commentary(data, as_of=date(2026, 2, 1))
    assert [r["title"] for r in s["recent"]] == ["Item 2"]
    assert s["catalyst_leads"] == []
    # Dated by the period, not by when Bullpen indexed it.
    assert [lt["firm"] for lt in s["letters"]["recent"]] == ["Old"]


def test_backtest_before_fetched_history_is_unknown_not_zero():
    data = bp.parse_ticker_payload(_payload([_item(1, "2026-10-20T00:00:00.000Z")], has_next=True))
    s = bp.summarize_commentary(data, as_of=date(2023, 1, 1))
    assert s["attention"]["90d"]["items"] is None
    assert s["attention"]["90d"]["complete"] is False


def test_paginated_count_is_marked_a_floor():
    data = bp.parse_ticker_payload(_payload([_item(1, "2026-10-20T00:00:00.000Z")], has_next=True))
    s = bp.summarize_commentary(data, as_of=date(2026, 10, 21))
    assert s["attention"]["365d"]["items"] == 1
    assert s["attention"]["365d"]["complete"] is False


FEED = """<?xml version="1.0"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
<item><title>Deal</title><link>https://bullpen.news/out/1?via=feed</link>
<pubDate>Wed, 21 Oct 2026 19:13:54 GMT</pubDate><dc:creator>A</dc:creator>
<category domain="ticker">BMBL</category><category>M&amp;A</category></item>
<item><title>Earnings</title><link>https://bullpen.news/out/2?via=feed</link>
<pubDate>Wed, 21 Oct 2026 13:00:00 GMT</pubDate><dc:creator>B</dc:creator>
<category domain="ticker">NFLX</category><category>Media</category></item>
<item><title>More</title><link>https://bullpen.news/out/3?via=feed</link>
<pubDate>Tue, 20 Oct 2026 13:00:00 GMT</pubDate><dc:creator>C</dc:creator>
<category domain="ticker">NFLX</category></item>
</channel></rss>"""


def test_feed_ideas_rank_catalysts_first_and_flag_new_names():
    ideas = bp.ideas_from_feed(bp.parse_feed(FEED), known={"NFLX"})
    assert [i["ticker"] for i in ideas] == ["BMBL", "NFLX"]
    assert ideas[0]["catalyst"] == ["M&A"]
    assert ideas[0]["in_universe"] is False
    assert ideas[1]["sources"] == ["B", "C"]
    assert bp.ideas_from_feed(bp.parse_feed(FEED))[0]["in_universe"] is None


def test_model_view_labels_opinion_and_unknown():
    assert (
        bp.commentary_for_model({"covered": False, "unavailable": "bullpen:rate_limited"})[
            "covered"
        ]
        is None
    )
    data = bp.parse_ticker_payload(_payload([_item(1, "2026-10-20T00:00:00.000Z", ("m-a",))]))
    view = bp.commentary_for_model(bp.summarize_commentary(data, as_of=date(2026, 10, 21)))
    assert "not facts" in view["note"]
    assert "url" not in view["recent"][0]
    assert view["catalyst_leads"][0]["catalyst"] == ["M&A"]


def test_leads_never_move_the_bolton_score():
    r = BoltonResult(ticker="KSS", passed=True, composite=61.5, tier="watch")
    data = bp.parse_ticker_payload(_payload([_item(1, "2026-10-20T00:00:00.000Z", ("activism",))]))
    attach_catalyst_leads(r, bp.summarize_commentary(data, as_of=date(2026, 10, 21)))
    assert (r.composite, r.tier, r.catalyst_checked) == (61.5, "watch", False)
    assert r.catalyst_leads and r.catalyst_leads[0]["catalyst"] == ["Activism"]
    assert r.buyside_items_90d == 1


def test_unavailable_leads_stay_unknown():
    r = BoltonResult(ticker="KSS", passed=True)
    attach_catalyst_leads(r, {"covered": False, "unavailable": "bullpen:rate_limited"})
    assert r.catalyst_leads is None and r.buyside_items_90d is None
    attach_catalyst_leads(r, {"covered": False})
    assert r.catalyst_leads == [] and r.buyside_items_90d == 0


def test_service_tells_a_refusal_from_a_404(monkeypatch):
    from hedge_fund.data.service import DataService

    ds = DataService.__new__(DataService)

    def registry(attempted: list[str]) -> SimpleNamespace:
        meta = SimpleNamespace(attempted=attempted, error="all providers returned no data")
        return SimpleNamespace(
            limiter=SimpleNamespace(wait_time=lambda _name: 0.0),
            get_with_meta=lambda *_a, **_k: (None, meta),
        )

    ds.registry = registry(["bullpen:no_data"])
    assert "unavailable" not in ds.get_commentary("ZZZZ")
    ds.registry = registry(["bullpen:rate_limited"])
    assert ds.get_commentary("ZZZZ")["unavailable"] == "bullpen:rate_limited"


def test_week_universe_uses_yahoo_spelling_and_refuses_an_empty_feed(monkeypatch):
    import hedge_fund.data.service as service
    from hedge_fund.data import universes

    feed = [{"tickers": ["BRK.B", "NFLX"]}, {"tickers": ["NFLX"]}]
    monkeypatch.setattr(
        service, "get_data_service", lambda: SimpleNamespace(get_commentary_feed=lambda: feed)
    )
    assert universes._bullpen_week() == ["BRK-B", "NFLX"]

    feed = []
    try:
        universes._bullpen_week()
    except ValueError:
        pass
    else:
        raise AssertionError("an empty feed must not become an empty universe")
