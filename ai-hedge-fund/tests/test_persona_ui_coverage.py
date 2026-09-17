"""Every investor the engine offers must be explainable to the reader.

An investor lives in two places that have to agree: the prompt preamble in
`personas.py`, which decides the verdict, and the profile in `profiles.py`,
which is what the app shows the reader when they ask how the verdict was
reached. Add a persona to one and not the other and the app either presents a
selectable investor it cannot describe, or describes one that cannot be run.

There used to be a third place — a hand-written note in the frontend's
`glossary.ts`. That was the real hazard: a second, independent description of
the same investor, in another language, which could tell the reader an
investor weighs one thing while the model had been told to weigh another. The
reader would then judge the verdict against a description that did not govern
it. It is gone; the profile is served from the backend, beside the prompt.

The display-name map in `PersonaOpinionCards.tsx` survives, because some cards
render a name before the persona query resolves, so it still has to be checked.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hedge_fund.agents.personas import (
    ALL_PERSONA_IDS,
    DEFAULT_COMMITTEE_PERSONAS,
    get_persona_system_prompt,
)
from hedge_fund.agents.profiles import PROFILES

CARDS = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "components"
    / "PersonaOpinionCards.tsx"
)


def _display_names() -> dict[str, str]:
    text = CARDS.read_text(encoding="utf-8")
    return dict(re.findall(r'^\s{4}([a-z_]+):\s*"([^"]+)",', text, re.M))


def test_prompts_and_profiles_describe_the_same_roster():
    prompts, profiles = set(ALL_PERSONA_IDS), set(PROFILES)
    assert prompts == profiles, (
        f"only a prompt: {sorted(prompts - profiles)}; only a profile: {sorted(profiles - prompts)}"
    )


def test_every_persona_has_a_display_name():
    missing = sorted(set(ALL_PERSONA_IDS) - set(_display_names()))
    assert not missing, f"no display name, so the UI prints the raw id: {missing}"


def test_display_names_match_the_profile_names():
    """One investor, one spelling, wherever the reader sees it."""
    names = _display_names()
    for pid, profile in PROFILES.items():
        if pid == "default":
            continue  # the card calls it "Analyst", the profile "House analyst"
        assert names.get(pid) == profile.name, (
            f"{pid}: card says {names.get(pid)!r}, profile says {profile.name!r}"
        )


def test_the_frontend_no_longer_keeps_its_own_descriptions():
    """Guards the fix, not the bug.

    If PERSONA_NOTES comes back, so does the drift it caused — a second
    description of an investor that no test can compare against the prompt.
    """
    glossary = CARDS.parent.parent / "lib" / "glossary.ts"
    text = glossary.read_text(encoding="utf-8")
    assert "export const PERSONA_NOTES" not in text


@pytest.mark.parametrize("pid", sorted(PROFILES))
def test_profiles_say_something_specific(pid: str):
    p = PROFILES[pid]
    assert p.name and not p.name.islower()
    assert len(p.who) > 30, f"{pid}: 'who' is too thin to be useful"
    assert len(p.style) > 80, f"{pid}: 'style' should be a few real lines"
    assert p.essence.endswith("."), f"{pid}: essence should read as one sentence"
    # The concrete checks are the point of the whole feature.
    assert len(p.tests) >= 3, f"{pid}: needs at least three concrete tests"
    for t in p.tests:
        assert len(t) > 15, f"{pid}: test too vague to audit a verdict against: {t!r}"


def test_the_committee_covers_distinct_approaches():
    """A committee of near-duplicates produces a confident, one-eyed consensus.

    These four are the axes the original four-person committee missed
    entirely: nobody asked what the macro regime was doing, nobody hunted the
    unloved, and nobody checked whether the multiple implied anything
    possible.
    """
    assert len(DEFAULT_COMMITTEE_PERSONAS) == len(set(DEFAULT_COMMITTEE_PERSONAS))
    for pid in DEFAULT_COMMITTEE_PERSONAS:
        assert pid in PROFILES, f"committee member with no profile: {pid}"
    for pid in ("anthony_bolton", "stanley_druckenmiller", "aswath_damodaran"):
        assert pid in DEFAULT_COMMITTEE_PERSONAS


def test_committee_fits_the_api_ceiling():
    from hedge_fund.api.routes.research import COMMITTEE_MAX

    assert len(DEFAULT_COMMITTEE_PERSONAS) <= COMMITTEE_MAX, (
        "the default committee cannot exceed the limit the endpoint enforces on "
        "a caller-supplied list"
    )


@pytest.mark.parametrize("pid", sorted(set(ALL_PERSONA_IDS) - {"default"}))
def test_each_persona_still_builds_a_prompt(pid: str):
    prompt = get_persona_system_prompt(pid)
    assert PROFILES[pid].name.split()[-1].lower() in prompt.lower(), (
        f"{pid}: the preamble does not mention the investor it is meant to imitate"
    )
