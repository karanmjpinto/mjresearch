"""The desk's investment principles, as data, and the ones it can enforce.

Most of this already existed. It was just never written down as principle: a
commodity avoid-list inside one screener's regex, a size band inside another's
constants, a concentration ceiling in the sizing module. Each arrived as a
threshold in a function rather than as a choice, which means nobody could read
the desk's philosophy without reading six files, and nothing stopped two of
them from contradicting each other.

**Four kinds, because they enforce in different places.** Conflating them is
why investment checklists become documents nobody executes:

  universe    where the desk will and will not look. Checked when a universe
              loads, before any company is fetched.
  exclusion   what it will not own regardless of the numbers. Matched on the
              sector and industry a company reports.
  threshold   a bar a screen can compute. These live in each screener's
              constants and are covered by the criteria fingerprint.
  judgment    something true and uncomputable. These are NOT scored. They go
              into the committee's prompt, and every screen row records that
              they were not checked.

That last kind is the one that matters most and is easiest to get wrong. A
principle like "a market leader in a defensible niche" or "management who
treat minorities fairly" cannot be read off a data feed. Turning it into a
number would produce a score that looks like the others and means nothing, and
this project's whole argument is that you should be able to tell those apart.
So they are registered here as explicitly unenforceable, which is a more
useful thing to record than a fabricated metric.

**On exclusions and what they actually catch.** The matching is on the sector
and industry *labels* a provider reports, not on revenue. A conglomerate
earning a fifth of its profit from tobacco through a subsidiary classified as
"Packaged Foods" will not be caught here. This is a coarse instrument that
removes the obvious cases; it is not a revenue screen, and it should not be
described to anyone as one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

PrincipleKind = Literal["universe", "exclusion", "threshold", "judgment"]


@dataclass(frozen=True)
class Principle:
    id: str
    #: The principle in the first person, as the desk's owner would state it.
    statement: str
    kind: PrincipleKind
    #: How it is enforced, or — for a judgment — why it cannot be.
    enforced: str
    #: Why it is held. A principle without a reason is a preference that will
    #: be abandoned the first time it costs something.
    why: str


# --- Exclusions -------------------------------------------------------------
#
# Deliberately separate patterns rather than one regex, so a row can say which
# principle removed a company. "Excluded" with no reason is the kind of silent
# filtering this project exists to refuse.

#: Gambling, tobacco and vaping. An ethical line, not an analytical one: these
#: are frequently excellent businesses on every number this app computes, which
#: is exactly why the exclusion has to be a rule rather than a judgment made
#: afresh each time a cheap one appears.
VICE_PATTERNS = re.compile(
    r"gambling|casino|resorts\s*&\s*casinos|betting|lotter|tobacco|cigarette|vap(e|ing)|nicotine",
    re.IGNORECASE,
)

#: Defence and weapons.
#:
#: Known to over-reach: the standard industry label is "Aerospace & Defense",
#: which does not separate a missile maker from a supplier of civil aircraft
#: seats. The label is excluded whole. That removes some companies this desk
#: would otherwise be happy to own, and the alternative — reading each one and
#: deciding — is a judgment, not a filter. Recorded here so the cost is known
#: rather than discovered.
DEFENCE_PATTERNS = re.compile(
    r"aerospace\s*&\s*defense|defense|defence|weapon|firearm|munition|ordnance",
    re.IGNORECASE,
)

#: Fossil fuel extraction. Narrower than the compounder's commodity-cyclical
#: avoid-list and held for a different reason: that list exists because
#: price-taking businesses do not compound, this one exists whatever the
#: economics. Extraction and drilling, not downstream chemicals or utilities.
FOSSIL_PATTERNS = re.compile(
    r"oil\s*&\s*gas|coal|thermal\s+coal|petroleum|exploration\s*&\s*production|drilling|"
    r"oil.*(e&p|extraction)|fossil",
    re.IGNORECASE,
)

#: Exclusion id → pattern. Order is the order they are reported in.
EXCLUSION_PATTERNS: dict[str, re.Pattern[str]] = {
    "vice": VICE_PATTERNS,
    "defence": DEFENCE_PATTERNS,
    "fossil-extraction": FOSSIL_PATTERNS,
}


def excluded_by(sector: str | None, industry: str | None) -> str | None:
    """Which exclusion principle removes this company, or None.

    Returns the principle id rather than a boolean, so a screen row can name
    the rule that removed it. A company dropped without a stated reason is
    indistinguishable from one that failed on the numbers.
    """
    text = f"{sector or ''} {industry or ''}".strip()
    if not text:
        return None
    for pid, pattern in EXCLUSION_PATTERNS.items():
        if pattern.search(text):
            return pid
    return None


# --- The registry -----------------------------------------------------------

REGISTRY: tuple[Principle, ...] = (
    Principle(
        id="quality-over-cheapness",
        statement="I buy good businesses at sensible prices, not bad businesses at low ones.",
        kind="threshold",
        enforced=(
            "The compounder screen's return-on-capital floor, cash-conversion test and "
            "reinvestment runway. Covered by the criteria fingerprint, so changing any "
            "of them invalidates every cached run rather than silently re-scoring it."
        ),
        why=(
            "Around 40% of the Russell 2000 has no earnings. Profitable US small caps "
            "returned roughly 14% annualised since 1963 against about 9% for "
            "unprofitable ones. Small is not an edge; it is a wider distribution, and "
            "the whole job is standing on the right side of it."
        ),
    ),
    Principle(
        id="small-and-mid-only",
        statement=(
            "I fish between roughly $500m and $20bn, where companies are large enough "
            "to disclose properly and small enough to be unexamined."
        ),
        kind="threshold",
        enforced="CAP_BAND_BY_CURRENCY, in the currency the company is quoted in.",
        why=(
            "About 18,000 listed companies worldwide sit under $10bn against roughly "
            "$100bn of dedicated mandates. The inefficiency is neglect, not cheapness. "
            "The floor is held at $500m deliberately: below it the coverage gap is "
            "wider still, but so are the spread, the disclosure and the time cost, and "
            "a desk run by one person has to be able to actually buy what it finds."
        ),
    ),
    Principle(
        id="no-dilution",
        statement="I will not own a business that funds itself by issuing shares to me.",
        kind="threshold",
        enforced="MAX_SHARE_CAGR_5Y, and the Kiyohara screen's issuance test.",
        why=(
            "A share count that grows is the clearest signal a business cannot fund "
            "its own growth, and it is the one quality measure that cannot be dressed "
            "up by an accounting choice."
        ),
    ),
    Principle(
        id="no-commodity-price-takers",
        statement="I will not own businesses whose earnings are set by a price they do not control.",
        kind="exclusion",
        enforced="AVOID_INDUSTRY_PATTERNS in the compounder screen.",
        why=(
            "An analytical exclusion, not an ethical one: a price-taker cannot compound, "
            "because any return above the cost of capital is competed away by the "
            "commodity cycle rather than defended by the business."
        ),
    ),
    Principle(
        id="vice",
        statement="I will not own gambling, tobacco or vaping businesses, whatever the numbers say.",
        kind="exclusion",
        enforced="VICE_PATTERNS, matched on reported sector and industry.",
        why=(
            "An ethical line rather than an analytical one. These are often excellent "
            "businesses by every measure this app computes, which is precisely why it "
            "has to be a standing rule: a judgment made afresh each time a cheap one "
            "appears is a judgment that eventually goes the other way."
        ),
    ),
    Principle(
        id="defence",
        statement="I will not own defence or weapons businesses.",
        kind="exclusion",
        enforced=(
            "DEFENCE_PATTERNS. Known to over-reach: the standard label is "
            "'Aerospace & Defense' and it is excluded whole, which also removes civil "
            "aerospace suppliers."
        ),
        why="An ethical line. The over-reach is accepted knowingly rather than discovered.",
    ),
    Principle(
        id="fossil-extraction",
        statement="I will not own fossil fuel extraction.",
        kind="exclusion",
        enforced="FOSSIL_PATTERNS.",
        why=(
            "An ethical line that happens to overlap the commodity-cyclical exclusion. "
            "Held separately because the reasons are different and either could change "
            "without the other."
        ),
    ),
    Principle(
        id="developed-markets-only",
        statement=(
            "In practice this desk only looks at developed markets with reliable "
            "disclosure and minority protection."
        ),
        # Deliberately NOT "universe": it is not enforced, and labelling it as
        # though it were is the exact failure this registry exists to prevent.
        kind="judgment",
        enforced=(
            "NOT ENFORCED — recorded, by choice, as a description of the current state "
            "rather than a rule. It is true today only because the eight universes "
            "happen to be the US, Japan, the UK, Germany, Canada and Australia. "
            "Adding one emerging-market universe would end it with nothing to catch "
            "the change.\n\n"
            "This is the same shape of defect as the compounder having no size filter "
            "and reading as a large-cap screen purely because of its default universe. "
            "It is left implicit on purpose, and the purpose of this entry is that the "
            "next person to add a universe reads this first."
        ),
        why=(
            "Disclosure quality and the treatment of minority shareholders are the two "
            "things a screen cannot measure and a foreign private investor cannot "
            "enforce."
        ),
    ),
    Principle(
        id="niche-leadership",
        statement="I want a defensible position in a niche, not a small share of a large market.",
        kind="judgment",
        enforced=(
            "NOT COMPUTABLE. A data feed carries a sector code, not a market share. "
            "Goes to the committee; every screen row records that business type and "
            "competitive position were never checked."
        ),
        why=(
            "It is the single most load-bearing judgment in small-cap investing and the "
            "one most often faked. Kiyohara's four P/E ceilings turn entirely on it, "
            "which is why that screen reports which ceiling a name is under and refuses "
            "to choose between them."
        ),
    ),
    Principle(
        id="aligned-owners",
        statement="I want founders or families with real money in the business beside mine.",
        kind="judgment",
        enforced=(
            "PARTLY. An aggregate insider percentage is available and used as a weak "
            "signal; who those insiders are is not in any feed. The screens say "
            "'closely held' at most and never claim to have identified a founder."
        ),
        why=(
            "Skin in the game is the cheapest available proxy for whether minority "
            "holders will be treated fairly, and the register is what the Japanese "
            "inheritance-tax trade turns on entirely."
        ),
    ),
    Principle(
        id="transition-not-failure",
        statement=(
            "A great business is punished once on the way up, and a halving is not by "
            "itself a reason to sell."
        ),
        kind="judgment",
        enforced=(
            "NOT COMPUTABLE, and deliberately not approximated. Ellenbogen's study found "
            "that in the ten years a 20% compounder compounded, one of those years it fell "
            "about 62% — usually not in a crash but during the attempt to become something "
            "larger. The fall is therefore evidence of nothing on its own.\n\n"
            "The two-act screen reports the drawdown from the five-year high and flags a "
            "name that is financially intact and down past 40% as a `transition_candidate`. "
            "That flag carries no score and is not a recommendation: it marks where the "
            "question has to be asked by a person. Scoring it would turn a quality screen "
            "into a falling-knife screen, which is the precise error this entry exists to "
            "forbid."
        ),
        why=(
            "It is the one judgment that decides whether a compounder is held or sold at the "
            "bottom, and the most expensive mistake in this strategy is made by selling: "
            "New Horizons sold Walmart, and that single position would have been worth more "
            "than the entire $8bn fund that inherited the decision."
        ),
    ),
    Principle(
        id="concentration",
        statement="I would rather own my tenth best idea twice than my twentieth at all.",
        kind="threshold",
        enforced="CONCENTRATION_WARN_PCT in decisions/sizing.py flags any position above 25% of book.",
        why=(
            "A book of fifty names is an index with extra steps, and the research cost "
            "per name is what makes the coverage gap exploitable in the first place."
        ),
    ),
    Principle(
        id="no-fabricated-numbers",
        statement="A language model never produces a figure I act on.",
        kind="threshold",
        enforced=(
            "Architectural. The planner chooses metrics and is shown no values; Python "
            "computes them; the narrator writes over results it did not produce and "
            "every numeric claim is re-checked against the frozen snapshot."
        ),
        why=(
            "A predicted figure can be correct, plausible and wrong in the same breath. "
            "This is the one principle the rest of the system is built to serve."
        ),
    ),
)

BY_KIND: dict[PrincipleKind, tuple[Principle, ...]] = {
    kind: tuple(p for p in REGISTRY if p.kind == kind)
    for kind in ("universe", "exclusion", "threshold", "judgment")
}


def judgments() -> tuple[Principle, ...]:
    """The principles no screen can check. For the committee prompt."""
    return BY_KIND["judgment"]
