"""The golden set: twenty cases with a binary contract each.

Every input is real. The tickers come from this app's own screen output —
EXE and TAP are the top two of the 86 names the Bolton screen passed, LULU sits
at the very bottom of its 52-week range, KSS is the levered contrarian case,
AAPL is the loved-and-expensive counter-example. Nothing here is invented to
reach twenty, which is the one rule of a golden set that cannot be bent: a
fabricated case makes the score meaningless in the direction that flatters you.

The spread is deliberate, because a set that is all happy paths measures
nothing:

    shape / coherence      8 cases   does the answer obey its own contract
    grounding              4 cases   is it about the data it was given
    persona adherence      5 cases   did the lens actually apply
    adversarial            3 cases   thin data, contradictions, a name the
                                     framework should reject

What this set does NOT claim: that SELL was correct on Kohl's. That is
unknowable, and a golden set that pretended otherwise would be the fabrication
this file exists to avoid. It measures whether the machinery did its job, not
whether the market agreed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evals import graders as g


@dataclass(frozen=True)
class Case:
    id: str
    #: Which fixture to feed it. See `evals/fixtures/` and `capture_fixtures`.
    fixture: str
    persona: str
    #: Why this case exists. If this is hard to write, the case is not earning
    #: its place.
    rationale: str
    checks: tuple[tuple[str, g.Grader], ...]
    #: Extra context handed to the graders.
    ctx: dict[str, Any] = field(default_factory=dict)
    category: str = "shape"


#: Checks every answer must pass, whatever the case. Kept separate so a new
#: case cannot accidentally ship without them.
BASELINE: tuple[tuple[str, g.Grader], ...] = (
    ("schema", g.schema_valid),
    ("conviction-range", g.conviction_in_range),
    ("stance-enum", g.stance_in_enum),
    ("stance-coherent", g.stance_matches_conviction),
    ("risks", g.risks_present_and_bounded),
)


CASES: tuple[Case, ...] = (
    # --- shape and coherence, across personas and companies ------------
    Case(
        id="shape-bolton-exe",
        fixture="EXE",
        persona="anthony_bolton",
        rationale="Top name of the 86 the Bolton screen passed. The case his lens is built for.",
        checks=BASELINE + (("thesis", g.thesis_is_substantial),),
        category="shape",
    ),
    Case(
        id="shape-bolton-tap",
        fixture="TAP",
        persona="anthony_bolton",
        rationale="Second Bolton name: 0.72x book, 8% up its range, insiders buying.",
        checks=BASELINE + (("thesis", g.thesis_is_substantial),),
        category="shape",
    ),
    Case(
        id="shape-buffett-kss",
        fixture="KSS",
        persona="warren_buffett",
        rationale="A quality lens on a cheap, levered retailer — the stance should be coherent either way.",
        checks=BASELINE,
        category="shape",
    ),
    Case(
        id="shape-graham-kss",
        fixture="KSS",
        persona="ben_graham",
        rationale="Same company, a different lens. Two personas on one fixture is how spread gets measured.",
        checks=BASELINE,
        category="shape",
    ),
    Case(
        id="shape-burry-lulu",
        fixture="LULU",
        persona="michael_burry",
        rationale="LULU sits at 0% of its 52-week range. The designated bear on a name at its floor.",
        checks=BASELINE,
        category="shape",
    ),
    Case(
        id="shape-damodaran-aapl",
        fixture="AAPL",
        persona="aswath_damodaran",
        rationale="A valuation lens on the most expensive fixture; conviction must still cohere with stance.",
        checks=BASELINE + (("thesis", g.thesis_is_substantial),),
        category="shape",
    ),
    Case(
        id="shape-druckenmiller-kss",
        fixture="KSS",
        persona="stanley_druckenmiller",
        rationale="A macro lens has the least data to work with here; the contract still holds.",
        checks=BASELINE,
        category="shape",
    ),
    Case(
        id="shape-wood-aapl",
        fixture="AAPL",
        persona="cathie_wood",
        rationale="A growth lens on a mature mega-cap. Coherence under a mismatched lens.",
        checks=BASELINE,
        category="shape",
    ),
    # --- grounding ------------------------------------------------------
    Case(
        id="ground-bolton-exe",
        fixture="EXE",
        persona="anthony_bolton",
        rationale="Bolton's lens is numeric, so it is the most likely to reach for a figure it was not given.",
        checks=BASELINE + (("no-invented-figures", g.no_invented_magnitudes),),
        category="grounding",
    ),
    Case(
        id="ground-graham-tap",
        fixture="TAP",
        persona="ben_graham",
        rationale="Graham cites book value and balance-sheet figures; check they come from the snapshot.",
        checks=BASELINE + (("no-invented-figures", g.no_invented_magnitudes),),
        category="grounding",
    ),
    Case(
        id="ground-damodaran-kss",
        fixture="KSS",
        persona="aswath_damodaran",
        rationale="The lens most likely to introduce a discount rate or growth figure of its own.",
        checks=BASELINE + (("no-invented-figures", g.no_invented_magnitudes),),
        category="grounding",
    ),
    Case(
        id="ground-buffett-lulu",
        fixture="LULU",
        persona="warren_buffett",
        rationale="Owner-earnings language invites invented cash-flow numbers.",
        checks=BASELINE + (("no-invented-figures", g.no_invented_magnitudes),),
        category="grounding",
    ),
    # --- persona adherence ---------------------------------------------
    Case(
        id="lens-bolton-rejects-expensive",
        fixture="AAPL",
        persona="anthony_bolton",
        rationale=(
            "The sharpest adherence test in the set. Bolton requires 'unloved'; AAPL is at "
            "45x book near its high. A high-conviction BUY here means the lens was ignored — "
            "and the live model got this right when tested by hand, so it is a real bar, not a "
            "hopeful one."
        ),
        checks=BASELINE + (("rejects-the-loved", g.not_a_high_conviction_buy),),
        category="persona",
    ),
    Case(
        id="lens-lou-mostly-passes",
        fixture="KSS",
        persona="norbert_lou",
        rationale="The punch-card lens is defined by declining. A confident BUY means it was dropped.",
        checks=BASELINE + (("declines-or-hedges", g.declines_or_hedges),),
        category="persona",
    ),
    Case(
        id="lens-lou-mostly-passes-aapl",
        fixture="AAPL",
        persona="norbert_lou",
        rationale="Same constraint on a completely different company; one instance could be luck.",
        checks=BASELINE + (("declines-or-hedges", g.declines_or_hedges),),
        category="persona",
    ),
    Case(
        id="lens-bolton-names-the-catalyst-gap",
        fixture="KSS",
        persona="anthony_bolton",
        rationale=(
            "His own rule is that cheap without a catalyst is a value trap, and KSS has no "
            "catalyst in the snapshot. He should raise the catalyst question or the trap."
        ),
        checks=BASELINE
        + (("engages-with-catalyst", g.mentions_any("catalyst", "value trap", "re-rat", "trap")),),
        category="persona",
    ),
    Case(
        id="lens-graham-names-leverage",
        fixture="KSS",
        persona="ben_graham",
        rationale=(
            "Graham's framework is downside protection and balance-sheet strength. KSS carries "
            "1.54x debt/equity and 2.1x interest cover — unavoidable for this lens."
        ),
        checks=BASELINE
        + (
            (
                "engages-with-balance-sheet",
                g.mentions_any("debt", "leverage", "interest", "balance sheet"),
            ),
        ),
        category="persona",
    ),
    # --- adversarial -----------------------------------------------------
    Case(
        id="adv-thin-data",
        fixture="THIN",
        persona="warren_buffett",
        rationale=(
            "A near-empty snapshot. The rules require saying so and lowering "
            "confidence_in_data; the failure mode is a confident thesis over nothing."
        ),
        checks=BASELINE + (("admits-thin-data", g.low_confidence_on_thin_data),),
        ctx={"thin_data": True},
        category="adversarial",
    ),
    Case(
        id="adv-thin-data-no-invention",
        fixture="THIN",
        persona="aswath_damodaran",
        rationale=(
            "The same empty snapshot given to the most numerate lens. If any case in the set "
            "produces invented figures, it is this one."
        ),
        checks=BASELINE
        + (
            ("admits-thin-data", g.low_confidence_on_thin_data),
            ("no-invented-figures", g.no_invented_magnitudes),
        ),
        ctx={"thin_data": True},
        category="adversarial",
    ),
    Case(
        id="adv-contradictory-bundle",
        fixture="CONTRADICTORY",
        persona="ben_graham",
        rationale=(
            "A snapshot whose price and valuation disagree by construction. The honest answer "
            "flags the inconsistency and lowers confidence rather than picking a side silently."
        ),
        checks=BASELINE + (("admits-thin-data", g.low_confidence_on_thin_data),),
        ctx={"thin_data": True},
        category="adversarial",
    ),
)


def by_category() -> dict[str, int]:
    out: dict[str, int] = {}
    for c in CASES:
        out[c.category] = out.get(c.category, 0) + 1
    return out
