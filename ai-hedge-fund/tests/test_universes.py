"""The index loaders, and the failure that took three of them out.

Every one of these lists is scraped, so the interesting cases are not "does it
parse" but "what does it do when the page changes underneath it". Three
loaders (NASDAQ-100, Dow 30, Russell 2000) silently stopped working in exactly
that way and nothing noticed until a screen came back empty.

No network here: the HTML is supplied. A test that fetches Wikipedia fails on a
train and passes for the wrong reasons on a good day.
"""

from __future__ import annotations

import pytest

from hedge_fund.data import universes

# The shape that matters: a changelog table of additions and removals sits on
# the real page *alongside* the constituents table, and it also has ticker-ish
# columns. Picking by position rather than shape is how you end up screening
# the companies that left the index.
_CHANGELOG = """
<table>
  <tr><th>Date</th><th>Added</th><th>Removed</th></tr>
  <tr><td>2026-01-02</td><td>OLDA</td><td>OLDB</td></tr>
</table>
"""

_CONSTITUENTS = """
<table>
  <tr><th>Symbol</th><th>Security</th></tr>
  {rows}
</table>
"""


def _page(n: int, *, changelog_first: bool = True) -> str:
    rows = "".join(f"<tr><td>TKR{i}</td><td>Company {i}</td></tr>" for i in range(n))
    table = _CONSTITUENTS.format(rows=rows)
    return (_CHANGELOG + table) if changelog_first else (table + _CHANGELOG)


def test_picks_the_constituents_table_not_the_changelog(monkeypatch):
    monkeypatch.setattr(universes, "_fetch_url_text", lambda url: _page(600))
    got = universes._fetch_sp_list("http://example.test", 600)
    assert len(got) == 600
    assert "OLDA" not in got and "OLDB" not in got


def test_order_of_tables_does_not_matter(monkeypatch):
    monkeypatch.setattr(universes, "_fetch_url_text", lambda url: _page(600, changelog_first=False))
    assert len(universes._fetch_sp_list("http://example.test", 600)) == 600


def test_a_short_table_is_refused(monkeypatch):
    """A page that renders a stub instead of the index must raise, not shrink.

    This is the actual regression: a truncated or placeholder table returning
    twelve names would otherwise become "the S&P 600", and a screen run over
    it would look like a completed run that simply found little.
    """
    monkeypatch.setattr(universes, "_fetch_url_text", lambda url: _page(12))
    with pytest.raises(ValueError, match="constituents table"):
        universes._fetch_sp_list("http://example.test", 600)


def test_symbols_are_normalised_for_yahoo():
    # Class shares are BRK.B upstream and BRK-B at Yahoo; the dot silently
    # returns no data rather than erroring.
    assert universes.normalize_yahoo_symbol("brk.b") == "BRK-B"
    assert universes.normalize_yahoo_symbol("  aapl ") == "AAPL"


def test_dedupe_preserves_order_and_drops_blanks():
    assert universes._dedupe(["A", "B", "A", "", "C"]) == ["A", "B", "C"]


def test_only_loadable_universes_are_offered():
    """Every advertised universe must have a loader, and vice versa.

    The UI builds its dropdown from UNIVERSE_META, so an entry with no loader
    is a choice that can only fail — which is what the dead NASDAQ-100, Dow
    and Russell 2000 entries were for months after their sources changed.
    """
    advertised = {u["id"] for u in universes.list_universe_meta()}
    assert advertised == set(universes.LOADERS), (
        "UNIVERSE_META and LOADERS disagree — one of them offers a universe the other cannot serve"
    )


def test_unknown_universe_is_rejected():
    with pytest.raises(ValueError, match="unknown universe"):
        universes.load_universe("russell2000")
