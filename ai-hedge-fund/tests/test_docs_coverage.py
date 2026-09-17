"""The reference section has to keep up with the app.

Documentation rots silently. Nothing breaks, no test fails, and the page just
slowly starts describing a different program — which is worse than having no
page, because a reader trusts it. The specific failure this guards is the one
that actually happens: a screen or a committee member is added, works, ships,
and is never mentioned anywhere a reader could find it.

So the invariant is narrow and mechanical: every screen the backend can serve,
and every investor who speaks by default, must appear in
`frontend/src/content/docs.ts`. It cannot check that the prose is *good* — but
it can refuse to let a feature exist that the docs have never heard of.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hedge_fund.agents.personas import DEFAULT_COMMITTEE_PERSONAS
from hedge_fund.agents.profiles import PROFILES
from hedge_fund.screeners import cache

DOCS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "content" / "docs.ts"


def _docs() -> str:
    assert DOCS.is_file(), f"the reference content is missing: {DOCS}"
    return DOCS.read_text(encoding="utf-8")


#: How each screen is referred to in prose. The docs call them by name rather
#: than by endpoint slug, so the check maps one to the other explicitly instead
#: of grepping for "bolton-contrarian" and passing on a word nobody reads.
SCREEN_PROSE = {
    "yartseva": "multibagger",
    "acquisition-compounder": "compounder",
    "bolton-contrarian": "Bolton",
}


@pytest.mark.parametrize("screen", sorted(cache.SCREENS))
def test_every_screen_is_documented(screen: str):
    assert screen in SCREEN_PROSE, (
        f"{screen!r} has no entry in SCREEN_PROSE — add the screen to the docs "
        "and name it here, so this test knows what to look for"
    )
    needle = SCREEN_PROSE[screen]
    assert needle.lower() in _docs().lower(), (
        f"the reference never mentions the {screen!r} screen (looked for "
        f"{needle!r}). A screen a reader cannot find out about is a screen "
        "they cannot judge."
    )


@pytest.mark.parametrize("pid", sorted(DEFAULT_COMMITTEE_PERSONAS))
def test_every_default_committee_member_is_documented(pid: str):
    """The committee list is a claim about whose judgment you are reading."""
    surname = PROFILES[pid].name.split()[-1]
    assert surname in _docs(), (
        f"{PROFILES[pid].name} speaks on every committee run but is not named in the reference."
    )


def test_the_determinism_labels_are_all_used():
    """A label defined and never applied is a legend entry for nothing."""
    text = _docs()
    for label in ("computed", "chosen-then-computed", "written", "judged"):
        # Once in the type/legend, at least once more as an item's `trust`.
        assert text.count(f'"{label}"') >= 2, (
            f"the {label!r} trust label is defined but never applied to a capability"
        )


def test_the_gaps_section_is_not_allowed_to_be_empty():
    """The honest list is load-bearing, not decoration.

    A reference that documents only what works teaches the reader to trust the
    parts that do not.
    """
    text = _docs()
    start = text.index("GAPS")
    assert text.count("[", start) >= 8, "the known-gaps list has been gutted"
    assert "not investment advice" in text
