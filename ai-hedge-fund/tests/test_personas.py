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


def test_default_committee_four():
    assert len(DEFAULT_COMMITTEE_PERSONAS) == 4


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
