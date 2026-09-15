"""Frameworks run against a company, and a page written back.

Two things are worth protecting here, and they are different in kind.

The applier must never invent a verdict. A checklist line that asks for a
judgment has to come back as a judgment even when a number is lying around
next to it, because a green tick against "management is honest" is a lie the
reader has no way to spot.

The writer must never destroy anything. It writes into a real Obsidian folder,
so every test below points it at a temporary directory and the refusals — an
existing file, a path climbing out of the vault — are asserted rather than
assumed.
"""

from __future__ import annotations

import pytest

from hedge_fund.knowledge.apply import (
    apply_framework,
    extract_criteria,
)
from hedge_fund.knowledge.writeback import (
    OUTPUT_FOLDER,
    WriteBackError,
    render,
    safe_stem,
    write,
)


@pytest.fixture(autouse=True)
def _isolated_vault(tmp_path, monkeypatch):
    """Every test gets its own empty vault. Nothing here touches a real one."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    from hedge_fund.settings import settings

    monkeypatch.setattr(settings, "vault_path", str(tmp_path), raising=False)
    return tmp_path


# --- pulling the checklist out of a note -------------------------------------

CHECKLIST = """---
tags: [framework]
---

# Quality checklist

## Economics

- Gross margin above 40%
- Operating margin at least 15%
- [ ] Return on invested capital over 12%

## The soft stuff

- Management is honest about mistakes
- Would I hold this if the market closed for five years
* Net debt no more than 2x EBITDA

Some prose that is not a criterion at all, just a sentence.

- ok
"""


def test_criteria_come_out_with_their_section() -> None:
    crits = extract_criteria(CHECKLIST)
    texts = [c.text for c in crits]
    assert "Gross margin above 40%" in texts
    assert "Return on invested capital over 12%" in texts, "checkbox lines are criteria"
    econ = next(c for c in crits if c.text.startswith("Gross margin"))
    assert econ.section == "Economics"
    soft = next(c for c in crits if c.text.startswith("Management"))
    assert soft.section == "The soft stuff"


def test_a_stub_line_is_not_a_criterion() -> None:
    """ "- ok" is a scratch line, not a test of anything."""
    assert "ok" not in [c.text for c in extract_criteria(CHECKLIST)]


def test_markup_is_stripped_so_the_line_reads_as_a_sentence() -> None:
    crits = extract_criteria("- **Gross margin** above [[Margins|40%]]\n")
    assert crits[0].text == "Gross margin above 40%"


# --- the part that must not invent a verdict ---------------------------------


METRICS = {
    "gross_margin": 0.46,
    "operating_margin": 0.11,
    "return_on_capital": 0.19,
    "net_debt": 1_000_000_000.0,
}


def _applied():
    return apply_framework("Quality checklist", "Frameworks/Quality.md", CHECKLIST, METRICS)


def test_a_stated_threshold_is_checked() -> None:
    a = _applied()
    gm = next(c for c in a.criteria if c.text.startswith("Gross margin"))
    assert gm.verdict == "met"
    assert gm.display == "46.0%"
    assert "against at least" in gm.because


def test_a_missed_threshold_says_missed() -> None:
    om = next(c for c in _applied().criteria if c.text.startswith("Operating margin"))
    assert om.verdict == "missed"
    assert om.display == "11.0%"


def test_a_percentage_threshold_is_compared_in_the_same_unit() -> None:
    """The metric is 0.46 and the line says 40. Comparing those raw fails every margin."""
    gm = next(c for c in _applied().criteria if c.text.startswith("Gross margin"))
    assert gm.threshold == 40.0
    assert gm.verdict == "met"


def test_a_judgment_line_stays_a_judgment() -> None:
    a = _applied()
    mgmt = next(c for c in a.criteria if c.text.startswith("Management"))
    assert mgmt.verdict == "judgment"
    assert mgmt.value is None, "no figure should be attached to a judgment"


def test_a_judgment_that_mentions_a_number_is_still_a_judgment() -> None:
    """ "hold for five years" has a number in it and is not a threshold."""
    hold = next(c for c in _applied().criteria if c.text.startswith("Would I"))
    assert hold.verdict == "judgment"


def test_an_unreported_metric_is_unmatched_not_failed() -> None:
    """A figure nobody publishes is a gap, and a gap is not a failed test."""
    a = apply_framework("f", "p", "- Gross margin above 40%\n", {})
    assert a.criteria[0].verdict == "unmatched"
    assert "not reported" in a.criteria[0].because


def test_a_line_about_nothing_measurable_is_unmatched() -> None:
    a = apply_framework("f", "p", "- The logo should be a serif wordmark\n", METRICS)
    assert a.criteria[0].verdict == "unmatched"


def test_a_metric_with_no_threshold_reports_the_figure_without_a_verdict() -> None:
    a = apply_framework("f", "p", "- Look at the gross margin trend over time\n", METRICS)
    c = a.criteria[0]
    assert c.verdict == "judgment"
    assert c.display == "46.0%", "the figure is still worth showing"
    assert "the call is yours" in c.because


def test_the_longest_phrase_wins_so_forward_pe_is_not_read_as_pe() -> None:
    a = apply_framework(
        "f", "p", "- Forward P/E under 20\n", {"pe_ratio": 40.0, "forward_pe": 18.0}
    )
    assert a.criteria[0].metric == "forward_pe"
    assert a.criteria[0].verdict == "met"


def test_the_summary_says_how_little_could_be_checked() -> None:
    a = apply_framework("f", "p", "- Management is honest\n- The team is aligned\n", METRICS)
    out = a.as_dict()
    assert out["answerable"] == 0
    assert "asks for judgments" in out["finding"]


def test_an_empty_note_is_not_an_error() -> None:
    out = apply_framework("f", "p", "just prose, no list", METRICS).as_dict()
    assert out["criteria"] == []
    assert "No checklist lines" in out["finding"]


# --- writing back, which must never destroy anything ------------------------


SECTIONS = {"The question": "Why would this be worth more?", "The decision": "- Call:"}


def test_render_touches_nothing(_isolated_vault) -> None:
    page = render("AAPL", name="Apple Inc.", sections=SECTIONS)
    assert page.exists is False
    assert not (_isolated_vault / OUTPUT_FOLDER).exists(), "preview must not create a folder"
    assert "Why would this be worth more?" in page.markdown


def test_the_note_lands_in_its_own_folder(_isolated_vault) -> None:
    page = render("AAPL", sections=SECTIONS)
    assert page.relative_path == f"{OUTPUT_FOLDER}/AAPL.md"
    write(page)
    assert (_isolated_vault / OUTPUT_FOLDER / "AAPL.md").is_file()


def test_it_refuses_to_overwrite(_isolated_vault) -> None:
    """The failure this rule exists for: a generated note is then hand-edited."""
    page = render("AAPL", sections=SECTIONS)
    write(page)
    target = _isolated_vault / OUTPUT_FOLDER / "AAPL.md"
    target.write_text("my own notes, edited by hand", encoding="utf-8")

    with pytest.raises(WriteBackError, match="already exists"):
        write(render("AAPL", sections=SECTIONS))
    assert target.read_text(encoding="utf-8") == "my own notes, edited by hand"


def test_render_reports_that_the_page_already_exists(_isolated_vault) -> None:
    write(render("AAPL", sections=SECTIONS))
    assert render("AAPL", sections=SECTIONS).exists is True


@pytest.mark.parametrize(
    "ticker",
    ["../../../etc/passwd", "..\\..\\windows", "A/B", "AAPL#x", "..", "."],
)
def test_a_ticker_cannot_climb_out_of_the_vault(_isolated_vault, ticker: str) -> None:
    """A symbol arrives from a URL, and `../` is a symbol as far as a format string knows."""
    try:
        page = render(ticker, sections=SECTIONS)
    except WriteBackError:
        return  # refused outright, which is also correct
    write(page)
    written = list(_isolated_vault.rglob("*.md"))
    assert written, "something should have been written"
    for w in written:
        assert w.resolve().is_relative_to(_isolated_vault.resolve())


def test_no_vault_is_a_clear_refusal_not_a_crash(monkeypatch) -> None:
    monkeypatch.delenv("VAULT_PATH", raising=False)
    from hedge_fund.settings import settings

    monkeypatch.setattr(settings, "vault_path", None, raising=False)
    with pytest.raises(WriteBackError, match="No vault is connected"):
        render("AAPL", sections=SECTIONS)


def test_a_filename_keeps_the_company_name_but_drops_what_obsidian_forbids() -> None:
    assert safe_stem("BRK.B", "Berkshire Hathaway") == "BRK.B — Berkshire Hathaway"
    assert "/" not in safe_stem("A/B", "Alpha/Beta")
    assert "#" not in safe_stem("X#Y", "Has#Hash")


def test_the_default_page_carries_frontmatter_and_the_links(_isolated_vault) -> None:
    page = render("AAPL", sections=SECTIONS, links=["Apple deep dive", "Semis 2026"])
    assert page.markdown.startswith("---")
    assert "[[Apple deep dive]]" in page.markdown
    assert page.template is None


# --- the reader's own template wins -----------------------------------------


class _FakeNote:
    def __init__(self, title: str, path: str) -> None:
        self.title = title
        self.path = path


class _FakeIndex:
    def __init__(self, notes) -> None:
        self.notes = notes


def test_a_template_in_the_vault_is_used_and_its_structure_kept(_isolated_vault) -> None:
    tpl = _isolated_vault / "Templates"
    tpl.mkdir()
    (tpl / "Value One Pager.md").write_text(
        "---\ntags: [one-pager]\n---\n\n# {{title}}\n\n## The question\n\n## My own section\n\n"
        "## The decision\n",
        encoding="utf-8",
    )
    index = _FakeIndex([_FakeNote("Value One Pager", "Templates/Value One Pager.md")])

    page = render("AAPL", name="Apple Inc.", sections=SECTIONS, index=index)
    assert page.template == "Value One Pager"
    assert "tags: [one-pager]" in page.markdown, "their frontmatter survives"
    assert "## My own section" in page.markdown, "their headings survive"
    assert "Why would this be worth more?" in page.markdown
    assert "{{title}}" not in page.markdown


def test_a_section_the_template_has_no_heading_for_is_appended_not_dropped(
    _isolated_vault,
) -> None:
    tpl = _isolated_vault / "T"
    tpl.mkdir()
    (tpl / "Value One Pager.md").write_text("# X\n\n## The question\n", encoding="utf-8")
    index = _FakeIndex([_FakeNote("Value One Pager", "T/Value One Pager.md")])

    page = render("AAPL", sections=SECTIONS, index=index)
    assert "The decision" in page.markdown, "an unplaced section must still appear"
