"""Persona registry and prompts."""

from __future__ import annotations

import pytest

from hedge_fund.agents.personas import (
    DEFAULT_COMMITTEE_PERSONAS,
    get_persona_system_prompt,
    is_valid_persona,
    list_persona_ids,
)


def test_list_includes_default_and_styles():
    ids = list_persona_ids()
    assert "default" in ids
    assert "warren_buffett" in ids
    assert len(ids) >= 8


def test_default_committee_is_several_distinct_voices():
    """Was pinned at exactly four; the count is not the property that matters.

    What matters is that the committee is plural, has no duplicates, and stays
    small enough to run — every member is a separate model call, so the list
    length is the run time. The reasoning about *which* voices, and the ceiling
    the endpoint enforces, are covered in test_persona_ui_coverage.py.
    """
    ids = DEFAULT_COMMITTEE_PERSONAS
    assert 4 <= len(ids) <= 8
    assert len(set(ids)) == len(ids)
    assert "default" not in ids, "the unstyled analyst is not a committee voice"


def test_is_valid_persona():
    assert is_valid_persona("Warren_Buffett") is True
    assert is_valid_persona("not_a_real_persona") is False


def test_get_persona_system_prompt_contains_rules():
    s = get_persona_system_prompt("ben_graham")
    assert "JSON" in s or "json" in s.lower()
    assert "stance" in s.lower() or "BUY" in s


def test_unknown_persona_raises():
    with pytest.raises(ValueError):
        get_persona_system_prompt("unknown_id")
