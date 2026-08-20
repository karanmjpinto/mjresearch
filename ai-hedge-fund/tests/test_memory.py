"""Methodology memory: what may be stored, and how it reaches a prompt."""

from __future__ import annotations

import pytest

from hedge_fund.agents import memory
from hedge_fund.agents.memory import MethodologyError

LESSON = "When comparing historical episodes, break the analysis out by asset class rather than reporting only an aggregate view."


def test_stores_and_lists_a_lesson(isolated_db):
    saved = memory.add_note(LESSON, tags=["case-studies"])
    assert saved["id"]
    assert memory.list_notes()[0]["note"] == LESSON


def test_whitespace_is_normalized(isolated_db):
    saved = memory.add_note("  Prefer   per-asset   panels.  ")
    assert saved["note"] == "Prefer per-asset panels."


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "Apple's fair value is $316.83",
        "Revenue came in at 1,250,000",
        "Set conviction to 85% conviction for this name",
    ],
)
def test_data_masquerading_as_method_is_rejected(bad):
    """A note that freezes a number would be applied, wrongly, to every later run."""
    with pytest.raises(MethodologyError):
        memory.scrub(bad)


def test_overlong_notes_are_rejected():
    with pytest.raises(MethodologyError, match="exceeds"):
        memory.scrub("x" * 5000)


def test_method_text_with_incidental_digits_is_accepted():
    assert memory.scrub("Require at least 3 years of history before claiming a trend.")


# ----------------------------------------------------------------------
# Retrieval scoping
# ----------------------------------------------------------------------


def test_global_notes_apply_everywhere(isolated_db):
    memory.add_note(LESSON)
    assert len(memory.retrieve(ticker="AAPL")) == 1
    assert len(memory.retrieve(ticker="MSFT")) == 1


def test_ticker_scoped_notes_do_not_leak(isolated_db):
    memory.add_note("Treat this name's reported margins with care.", scope_ticker="AAPL")
    assert len(memory.retrieve(ticker="AAPL")) == 1
    assert len(memory.retrieve(ticker="MSFT")) == 0


def test_persona_scoped_notes_do_not_leak(isolated_db):
    memory.add_note("Weight owner earnings over reported EPS.", scope_persona="warren_buffett")
    assert len(memory.retrieve(persona="warren_buffett")) == 1
    assert len(memory.retrieve(persona="cathie_wood")) == 0


def test_specific_notes_outrank_global_ones(isolated_db):
    for i in range(memory.MAX_NOTES_IN_PROMPT):
        memory.add_note(f"Global guidance number {i} about method.")
    memory.add_note("Specific guidance for this name.", scope_ticker="AAPL")

    retrieved = memory.retrieve(ticker="AAPL")
    assert len(retrieved) == memory.MAX_NOTES_IN_PROMPT
    assert retrieved[0]["scope_ticker"] == "AAPL"


def test_deactivated_notes_stop_being_retrieved(isolated_db):
    note = memory.add_note(LESSON)
    assert memory.deactivate_note(note["id"]) is True
    assert memory.retrieve() == []
    assert len(memory.list_notes(include_inactive=True)) == 1


def test_deactivating_a_missing_note_is_reported(isolated_db):
    assert memory.deactivate_note(9999) is False


def test_usage_is_counted_when_a_run_applies_a_note(isolated_db):
    from hedge_fund.runs import RunRecord, save_run

    note = memory.add_note(LESSON)
    save_run(
        RunRecord(
            ticker="AAPL",
            mode="single",
            snapshot={"ticker": "AAPL"},
            methodology_note_ids=[note["id"]],
        )
    )
    assert memory.list_notes()[0]["times_applied"] == 1


# ----------------------------------------------------------------------
# Prompt rendering
# ----------------------------------------------------------------------


def test_no_notes_renders_nothing(isolated_db):
    assert memory.render_for_prompt([]) == ""


def test_rendered_section_contains_the_lesson(isolated_db):
    memory.add_note(LESSON)
    rendered = memory.render_for_prompt(memory.retrieve(ticker="AAPL"))
    assert "Learned methodology" in rendered
    assert LESSON in rendered


def test_rendered_section_labels_scope(isolated_db):
    memory.add_note("Discount reported margins here.", scope_ticker="AAPL")
    assert "[AAPL]" in memory.render_for_prompt(memory.retrieve(ticker="AAPL"))


def test_retrieval_failure_is_survivable(monkeypatch):
    """Memory is an enhancement; losing it must not fail the analysis."""

    def boom(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(memory, "list_notes", boom)
    assert memory.retrieve(ticker="AAPL") == []
