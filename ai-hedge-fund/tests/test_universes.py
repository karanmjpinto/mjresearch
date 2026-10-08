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


def test_japanese_codes_become_yahoo_symbols():
    """`7203` is `7203.T` at Yahoo, and the dot must survive.

    `normalize_yahoo_symbol` turns a dot into a hyphen for US class shares, so
    running a Tokyo code through it produces `7203-T` — a symbol that returns
    no data rather than an error, which is how an entire universe silently
    becomes a list of names with no financials.
    """
    assert universes.jp_symbol("7203") == "7203.T"
    assert universes.jp_symbol(" 83 ") == "0083.T", "leading zeros survive a spreadsheet"
    assert universes.jp_symbol("160a") == "160A.T", "codes are alphanumeric now"


def _jpx_frame(rows):
    import pandas as pd

    return pd.DataFrame(
        rows,
        columns=["Local Code", "Section/Products", "Size (New Index Series)"],
    )


def test_the_japan_loader_keeps_only_domestic_companies_in_the_right_size_bands(monkeypatch):
    """The file carries 485 ETFs, plus REITs, foreign listings and PRO names.

    Taking it whole would put exchange-traded funds into a screen that reads
    company balance sheets.
    """
    import pandas as pd

    rows = [[f"{3000 + i}", "Prime Market (Domestic)", "TOPIX Mid400"] for i in range(400)]
    rows += [[f"{5000 + i}", "Standard Market(Domestic)", "TOPIX Small 1"] for i in range(400)]
    rows += [["1306", "ETFs/ ETNs", "-"]]
    rows += [["8951", "REIT, Venture Funds, Country Funds and Infrastructure Funds", "-"]]
    rows += [["9999", "Prime Market (Domestic)", "TOPIX Core30"]]

    monkeypatch.setattr(universes, "_fetch_url_bytes", lambda url: b"")
    monkeypatch.setattr(pd, "read_excel", lambda *a, **k: _jpx_frame(rows))

    got = universes.fetch_jp_mid_small()
    assert len(got) == 800
    assert "1306.T" not in got and "8951.T" not in got
    assert "9999.T" not in got, "Core30 is the hundred names every institution already owns"


def test_a_shrunken_japan_file_raises_rather_than_returning_a_short_universe(monkeypatch):
    """If JPX renames the size bands the filter matches nothing.

    An empty universe reads downstream as a market with no companies in it,
    not as a broken loader — the same failure that took out the Dow and
    NASDAQ-100 lists for months.
    """
    import pandas as pd

    monkeypatch.setattr(universes, "_fetch_url_bytes", lambda url: b"")
    monkeypatch.setattr(
        pd,
        "read_excel",
        lambda *a, **k: _jpx_frame([["7203", "Prime Market (Domestic)", "TOPIX Renamed"]]),
    )
    with pytest.raises(ValueError, match="mid/small names"):
        universes.fetch_jp_mid_small()


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
