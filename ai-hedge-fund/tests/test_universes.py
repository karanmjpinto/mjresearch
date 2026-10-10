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


def test_exchange_symbols_hyphenate_the_class_before_adding_the_exchange():
    """`RCI.B` in Toronto is `RCI-B.TO` at Yahoo, never `RCI-B-TO`.

    Appending the suffix first and normalising afterwards is the silent
    version of this bug: it produces a symbol that returns no data, so the
    company reads as one with no financials rather than a mistyped ticker.
    """
    assert universes.exchange_symbol("RCI.B", ".TO") == "RCI-B.TO"
    assert universes.exchange_symbol(" bhp ", ".AX") == "BHP.AX"
    assert universes.exchange_symbol("AIXA", ".DE") == "AIXA.DE"
    assert universes.exchange_symbol("3IN", ".L") == "3IN.L"
    assert universes.exchange_symbol("AAPL") == "AAPL", "no suffix is still valid"
    assert universes.exchange_symbol("  ") == "", "blanks are dropped, not suffixed"


def _wiki_page(column: str, rows: list[str]) -> str:
    body = "".join(f"<tr><td>Company {i}</td><td>{t}</td></tr>" for i, t in enumerate(rows))
    return f"""
    {_CHANGELOG}
    <table>
      <tr><th>Company</th><th>{column}</th></tr>
      {body}
    </table>
    """


def test_the_uk_loader_reads_a_ticker_column_and_suffixes_for_london(monkeypatch):
    """The FTSE 250 article calls the column "Ticker", not "Symbol".

    The S&P loaders hardcoded "Symbol", which is why this needed the column
    to become a parameter rather than a second near-identical function.
    """
    rows = [f"TK{i}" for i in range(250)]
    monkeypatch.setattr(universes, "_fetch_url_text", lambda url: _wiki_page("Ticker", rows))
    got = universes.fetch_uk_mid()
    assert len(got) == 250
    assert got[0] == "TK0.L"
    assert all(s.endswith(".L") for s in got)


def test_the_german_loader_suffixes_for_xetra(monkeypatch):
    rows = [f"SY{i}" for i in range(52)]
    monkeypatch.setattr(universes, "_fetch_url_text", lambda url: _wiki_page("Symbol", rows))
    got = universes.fetch_de_mid()
    assert len(got) == 52, "a couple of rows over 50 during an index change is fine"
    assert all(s.endswith(".DE") for s in got)


def test_a_wiki_table_with_no_ticker_column_is_refused(monkeypatch):
    """This is why SDAX is not a universe.

    Its article renders Logo, Name, Industry and Location — the companies are
    named and the symbols are absent. Matching on row count alone would
    return a list of German place names suffixed `.DE`.
    """
    monkeypatch.setattr(
        universes,
        "_fetch_url_text",
        lambda url: _wiki_page("Location", [f"City {i}" for i in range(70)]),
    )
    with pytest.raises(ValueError, match="constituents table"):
        universes._fetch_wiki_list("http://example.test", "Symbol", 70, ".DE")


def test_the_australian_loader_skips_the_banner_and_suffixes_for_the_asx(monkeypatch):
    banner = "ASX listed companies as at 1 Jan 2026\n"
    header = "Company name,ASX code,GICS industry group\n"
    body = "".join(f"Company {i},C{i:03d},Capital Goods\n" for i in range(1500))
    monkeypatch.setattr(
        universes, "_fetch_url_bytes", lambda url: (banner + header + body).encode()
    )
    got = universes.fetch_au_all()
    assert len(got) == 1500
    assert got[0] == "C000.AX"


def test_a_truncated_asx_file_raises_rather_than_shrinking_the_market(monkeypatch):
    banner = "ASX listed companies\n"
    header = "Company name,ASX code,GICS industry group\n"
    monkeypatch.setattr(
        universes,
        "_fetch_url_bytes",
        lambda url: (banner + header + "Only Co,ONE,Banks\n").encode(),
    )
    with pytest.raises(ValueError, match="expected ~1900"):
        universes.fetch_au_all()


def _tsx_payload(rows):
    import json as _json

    return _json.dumps({"results": rows}).encode()


def test_the_canadian_loader_drops_the_fund_complex(monkeypatch):
    """Two thirds of Toronto's directory is not an operating company.

    A quality screen reading ROIC and FCF conversion over closed-end funds
    and preferred series is the Canadian version of putting 485 ETFs into a
    Japanese balance-sheet screen.
    """
    rows = [{"symbol": f"CO{i}", "name": f"Operating Company {i}"} for i in range(500)]
    rows += [
        {"symbol": "IGBT.UN", "name": "2028 Investment Grade Bond Trust"},
        {"symbol": "ENB.PR.A", "name": "Enbridge Preferred Series A"},
        {"symbol": "XIU", "name": "iShares S&P/TSX 60 Index ETF"},
        {"symbol": "DFN", "name": "Dividend 15 Split Corp"},
        {"symbol": "ABC.DB", "name": "Some Issuer Convertible Debenture"},
    ]
    # A class share is a company and must survive both filters.
    rows += [{"symbol": "RCI.B", "name": "Rogers Communications Inc"}]

    monkeypatch.setattr(universes, "_fetch_url_bytes", lambda url: _tsx_payload(rows))
    got = universes.fetch_ca_all()

    assert "RCI-B.TO" in got, "class B shares are a company, not a series"
    for dropped in ("IGBT-UN.TO", "XIU.TO", "DFN.TO", "ABC-DB.TO"):
        assert dropped not in got
    assert len(got) == 501


def test_an_empty_tsx_directory_raises(monkeypatch):
    monkeypatch.setattr(universes, "_fetch_url_bytes", lambda url: _tsx_payload([]))
    with pytest.raises(ValueError, match="no results"):
        universes.fetch_ca_all()


def test_a_tsx_directory_of_only_funds_raises_rather_than_returning_a_stub(monkeypatch):
    rows = [{"symbol": f"F{i}.UN", "name": f"Fund {i}"} for i in range(300)]
    monkeypatch.setattr(universes, "_fetch_url_bytes", lambda url: _tsx_payload(rows))
    with pytest.raises(ValueError, match="expected ~800"):
        universes.fetch_ca_all()


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


def _frontend(rel: str) -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[1] / "frontend" / "src" / rel).read_text()


def test_the_two_default_universe_maps_agree():
    """`DEFAULT_UNIVERSE_FOR` exists twice, in two languages.

    Once in `api/routes/screeners.py`, which the refresh script reads to decide
    what to recompute, and once in `frontend/src/lib/universes.ts`, which the
    screener view reads to decide what to show. Nothing connected them, so
    re-pointing the compounder at the mid-cap index in one of the two would
    have left the UI asking for a universe the script never builds — a screen
    that is permanently "nothing computed yet" and a cache nobody reads.

    Parsed rather than imported, for the reason the persona coverage test
    gives: the frontend copy is TypeScript, and a second hand-written mirror
    in Python would just be a third place to disagree.
    """
    import re

    from hedge_fund.api.routes.screeners import DEFAULT_UNIVERSE_FOR as backend

    ts = _frontend("lib/universes.ts")
    block = re.search(
        r"DEFAULT_UNIVERSE_FOR:\s*Record<string,\s*string>\s*=\s*\{(.*?)\n\};",
        ts,
        re.S,
    )
    assert block, "could not find DEFAULT_UNIVERSE_FOR in universes.ts"

    frontend = dict(re.findall(r"\"?([a-z0-9-]+)\"?:\s*\"([a-z0-9_]+)\"", block.group(1)))
    assert frontend, "parsed no entries — the literal's shape changed"
    assert frontend == backend, (
        "the frontend and backend per-screen default universes disagree:\n"
        f"  frontend: {frontend}\n  backend:  {backend}"
    )


def test_every_default_universe_is_one_that_loads():
    """A screen pointed at a universe with no loader can only fail."""
    from hedge_fund.api.routes.screeners import DEFAULT_UNIVERSE, DEFAULT_UNIVERSE_FOR

    for screen, uid in DEFAULT_UNIVERSE_FOR.items():
        assert uid in universes.LOADERS, f"{screen} defaults to unloadable {uid!r}"
    assert DEFAULT_UNIVERSE in universes.LOADERS
