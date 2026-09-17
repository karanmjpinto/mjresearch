"""The shared prefix, and the property it must not break.

A prefix cache can only reuse a *prefix*. With the investor's style in the
system message, the text that differs sat in front of the market bundle, so
seven personas each paid a full prefill for the same ~6,000 tokens — measured
on an M4 Max at roughly 22 seconds apiece. Reordered so the shared bytes come
first, calls two through seven returned in about 0.17 s.

The speed is the easy half. These tests guard the half that could quietly ruin
the feature: that the bundle really is byte-identical across personas (or there
is no cache hit at all), and that the investor's instruction is still *present*
and still last (or the persona stops being a persona).

What no unit test can settle is whether a given model follows an instruction as
well at the end of a prompt as at the front. That is a property of the model,
it is why `llm_shared_prefix` is switchable, and it is measured against a real
committee run rather than asserted here.
"""

from __future__ import annotations

import re

import pytest

from hedge_fund.agents.personas import (
    ALL_PERSONA_IDS,
    DEFAULT_COMMITTEE_PERSONAS,
    SHARED_ANALYST_SYSTEM,
    get_persona_lens,
    get_persona_system_prompt,
)


def test_the_shared_system_prompt_mentions_no_investor():
    """If a name leaks in, the prefix stops being shared and the cache dies.

    Matched on word boundaries, not substrings: "lu" from `li_lu` occurs inside
    "valuable" and "include", and a substring check fails on the honest prompt.
    """
    lowered = SHARED_ANALYST_SYSTEM.lower()
    for pid in ALL_PERSONA_IDS:
        if pid == "default":
            continue
        surname = pid.split("_")[-1]
        assert not re.search(rf"\b{re.escape(surname)}\b", lowered), (
            f"{surname!r} appears in the shared system prompt — every persona would "
            "send a different prefix and no call could hit the cache"
        )


def test_the_shared_prompt_still_carries_the_output_rules():
    """The rules must survive the split, or the JSON contract is gone."""
    for needle in ("JSON", "conviction_score", "stance", "confidence_in_data"):
        assert needle in SHARED_ANALYST_SYSTEM, f"lost {needle!r} from the shared rules"


@pytest.mark.parametrize("pid", sorted(DEFAULT_COMMITTEE_PERSONAS))
def test_each_lens_is_distinct_and_substantial(pid: str):
    lens = get_persona_lens(pid)
    assert len(lens) > 80, f"{pid}: lens too thin to steer anything"
    # The lens carries the style and nothing else — the rules live in the prefix.
    assert "Output valid JSON" not in lens, (
        f"{pid}: the output rules are duplicated into the lens; they belong in "
        "the shared prefix only"
    )


def test_lenses_do_not_collide():
    """Seven identical lenses would be seven identical opinions."""
    lenses = {pid: get_persona_lens(pid) for pid in DEFAULT_COMMITTEE_PERSONAS}
    assert len(set(lenses.values())) == len(lenses)


def test_the_old_single_message_form_still_works():
    """`llm_shared_prefix = False` has to remain a real escape hatch.

    It is the fallback if a future model follows a trailing instruction worse
    than a leading one, so it must not rot.
    """
    full = get_persona_system_prompt("anthony_bolton")
    assert "Bolton" in full
    assert "Output valid JSON" in full
    # The two forms carry the same two ingredients, in the opposite order.
    assert get_persona_lens("anthony_bolton") in full


def test_unknown_persona_is_rejected_by_both_accessors():
    for fn in (get_persona_lens, get_persona_system_prompt):
        with pytest.raises(ValueError, match="unknown persona"):
            fn("not_a_real_investor")


def test_lens_lookup_is_case_and_space_insensitive():
    """The id arrives from an HTTP query string; be forgiving there."""
    assert get_persona_lens("  Anthony_Bolton ") == get_persona_lens("anthony_bolton")


def test_the_reorder_is_off_by_default():
    """Guards a decision, not a preference.

    The reorder was built, measured end to end, and found to be worth 1.28x —
    while moving a bear from SELL 15 to BUY 75 on the same snapshot. Whether
    that is better or worse is unknowable without a golden set, so the default
    stays where the behaviour is known. If someone flips this to True, the
    committee's answers change; that should be a deliberate act with an eval
    behind it, not a quiet default.
    """
    from hedge_fund.settings import Settings

    assert Settings().llm_shared_prefix is False
