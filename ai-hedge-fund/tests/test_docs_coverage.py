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

import re
from pathlib import Path

import pytest

from hedge_fund.agents.personas import DEFAULT_COMMITTEE_PERSONAS
from hedge_fund.agents.profiles import PROFILES
from hedge_fund.screeners import cache, principles

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
    "kiyohara-handbook": "Kiyohara",
    "ellenbogen-two-act": "Ellenbogen",
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


@pytest.mark.parametrize("pid", sorted(principles.EXCLUSION_PATTERNS))
def test_every_standing_exclusion_is_documented(pid: str):
    """An exclusion the reference never mentions is a rule nobody can audit.

    These remove companies before anything is measured and across every
    screen, so they shape every list the app produces. Same reasoning as the
    screen and committee coverage tests above: the docs cannot be made to be
    good, but they can be made to be complete.
    """
    assert pid in _docs().lower(), (
        f"the reference never mentions the {pid!r} exclusion. It silently removes "
        "companies from every screen, which is exactly the kind of rule a reader "
        "has to be able to find."
    )


def test_the_unenforced_geography_principle_is_disclosed():
    """The registry admits this one is not enforced; the docs must too.

    It is the principle most likely to be read as a guarantee, and the one
    that would vanish without trace the moment a universe is added.
    """
    text = _docs().lower()
    assert "not enforced" in text, (
        "the docs do not disclose that the developed-markets principle is "
        "unenforced, so a reader would take it as a rule the app applies"
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


#: Numbers in the prose that are really counts of something the code owns.
#:
#: The screen and committee checks above catch a *missing* feature. They do not
#: catch the other half of the same rot: a count that was right when it was
#: written and is now off by one because something was added beside it. That is
#: what actually happened — the reference said "three screens" and "only three
#: universes load" for a release after the fourth of each had shipped, and
#: nothing failed.
#:
#: Spelled out in words because that is how the page reads, and the page is the
#: artefact under test.
_NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


def _count_word(n: int, noun: str) -> str:
    """The English word for `n`, or a failure that says what to do about it."""
    word = _NUMBER_WORDS.get(n)
    assert word is not None, (
        f"there are now {n} {noun} — extend _NUMBER_WORDS past ten so this check keeps working"
    )
    return word


def test_the_screen_count_in_the_prose_is_the_real_one():
    """ "The four screens" has to still say four."""
    n = len(cache.SCREENS)
    word = _count_word(n, "screens")
    # Lower-cased on both sides: the stale count is just as wrong mid-sentence
    # ("all three screens") as it is in the heading, and matching the capital
    # would also fail a correct page that rephrased the heading.
    text = _docs().lower()
    assert f"{word} screens" in text, (
        f"there are {n} screens, so the reference should head that list "
        f'"The {word} screens" — it currently does not, which means the count '
        "drifted when a screen was added"
    )
    for other, w in _NUMBER_WORDS.items():
        if other != n:
            assert f"{w} screens" not in text, (
                f'the reference still says "{w} screens" somewhere while {n} exist'
            )


#: Everything under here is copy a user reads. The reference page is not the
#: only place that states a count.
FRONTEND_SRC = DOCS.parents[1]


def _without_comments(src: str) -> str:
    """Drop `//` and block comments, so only strings a user can see remain.

    Comments in this codebase narrate history on purpose — ScreenersView says
    "only two screens can actually be run live", which is true, and
    screeners.ts explains a ternary that was "fine for two screens". Those are
    correct sentences about the past and about a subset, and a check that
    cannot tell them from a heading would be turned off within a week.
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", src, flags=re.M)


def test_no_user_facing_copy_states_a_stale_screen_count():
    """The count has to be right on every screen it appears on, not just one.

    `DeploymentLimits.tsx` told visitors to the hosted site about "the three
    screens" for a whole release after the fourth landed — the reference page
    had been corrected and this had not, so the two user-facing surfaces
    disagreed three clicks apart. A check scoped to one file cannot catch
    that, so this one reads them all.
    """
    n = len(cache.SCREENS)
    stale = []
    for path in sorted(FRONTEND_SRC.rglob("*.ts*")):
        text = _without_comments(path.read_text(encoding="utf-8")).lower()
        for other, w in _NUMBER_WORDS.items():
            if other != n and f"{w} screens" in text:
                stale.append(f"{path.relative_to(FRONTEND_SRC.parent)}: {w!r} screens")
    assert not stale, (
        f"there are {n} screens, but this copy still names another count:\n  " + "\n  ".join(stale)
    )


def test_the_universe_count_in_the_prose_is_the_real_one():
    """The honest list names how many universes load. Loaders get added."""
    from hedge_fund.data.universes import UNIVERSE_META

    n = len(UNIVERSE_META)
    word = _count_word(n, "universes")
    text = _docs().lower()
    assert f"{word} universes load" in text, (
        f'{n} universes load, so the gap should read "Only {word} universes load"'
    )
    for other, w in _NUMBER_WORDS.items():
        if other != n:
            assert f"{w} universes load" not in text, (
                f'the gap still claims "{w} universes load" while {n} do'
            )


def test_the_regime_chain_is_documented_while_it_is_fitted_by_default():
    """The HMM shipped on by default, and the docs denied it existed.

    `/api/regimes` fits the chain unless asked not to, and the panel renders
    its persistence and next-day share. For a release the reference said the
    regimes "do not say which regime comes next" — a true statement about the
    clustering, printed on a page describing an app that had stopped being only
    the clustering. If the default flips back, this test should go with it.
    """
    import inspect

    from hedge_fund.regimes import detect

    param = inspect.signature(detect.analyse).parameters.get("with_hmm")
    if param is not None and param.default is not True:
        pytest.skip("the chain is no longer fitted by default")

    text = _docs().lower()
    assert "hidden markov" in text, (
        "the Regimes tab fits a hidden Markov model by default and reports its "
        "transition matrix; the reference never mentions it"
    )
    assert "baum-welch" in text or "transition matrix" in text, (
        "the chain is documented by name only — say what it is fitted by or "
        "what it is there for, since its one unique output is the transitions"
    )
