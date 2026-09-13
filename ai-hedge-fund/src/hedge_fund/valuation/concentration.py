"""How concentrated your conviction entitles you to be.

Damodaran's point, and the reason this is a separate step from sizing: a
diversified portfolio is an admission that you do not have conviction. That is
not a criticism — it is the correct response to not having one. What is
incoherent is claiming high conviction and holding forty names, or holding six
names on a thesis whose own weakest leg is unanswered.

So this runs in both directions.

Forwards, it turns a conviction score into the largest position it justifies,
and says what book that implies. Backwards — the more useful direction — it
takes the book you actually hold and reports the conviction you are implicitly
claiming by holding it. Most people find the second number uncomfortable, which
is the point of computing it.

The bands are a stated policy, not a derivation. There is a temptation to reach
for Kelly here and produce a number to three decimal places; Kelly needs an edge
and a payoff you can actually estimate, and if you could estimate those you
would not need the conviction chain in the first place. Dressing a judgment as
arithmetic is the specific failure this whole module exists to catch, so the
policy is written down, attributed, and adjustable rather than hidden inside a
formula.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

#: Conviction band → the largest single position it justifies, as a percentage
#: of the book. Read the `because` text as the actual reasoning; the number is
#: a consequence of it, not the other way round.
#:
#: The top band is deliberately not open-ended. Even a thesis where all three
#: requisites hold is a thesis about the future, and the history of
#: concentrated investing is mostly people who were right about the business
#: and wrong about the timing.
BANDS: tuple[tuple[float, float, str], ...] = (
    (
        0.50,
        15.0,
        "All three requisites hold. This is the band where concentration is the "
        "correct response — you have an edge, a reason the market corrects, and "
        "a horizon that covers it.",
    ),
    (
        0.20,
        8.0,
        "Two requisites hold and one is soft. Big enough to matter to the book, "
        "small enough that the soft leg being wrong is survivable.",
    ),
    (
        0.05,
        4.0,
        "The chain holds only weakly. A position this size is a research note "
        "with money attached — it earns you attention, not a return.",
    ),
    (
        0.0,
        2.0,
        "Conviction is close to absent. If you want the exposure, you are "
        "buying the sector, not this company — size it as such or skip it.",
    ),
)

#: Below this, "how many names does that imply" stops being a useful question:
#: the answer is an index fund, and saying so is more honest than printing 60.
INDEX_THRESHOLD_NAMES = 40


class ConcentrationError(ValueError):
    """An input was unusable. The caller is told which."""


@dataclass(frozen=True)
class Band:
    max_weight_pct: float
    because: str
    implied_names: int
    implied_names_note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_weight_pct": self.max_weight_pct,
            "because": self.because,
            "implied_names": self.implied_names,
            "implied_names_note": self.implied_names_note,
        }


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def band_for(conviction: float) -> Band:
    """The concentration policy for a conviction score."""
    c = _clamp01(float(conviction))
    for floor, weight, because in BANDS:
        if c >= floor:
            names = math.ceil(100.0 / weight)
            note = (
                f"At {weight:.0f}% a book is about {names} names."
                if names < INDEX_THRESHOLD_NAMES
                else (
                    f"At {weight:.0f}% a book is {names}+ names, which is an index "
                    "fund with extra steps. Buy the index and spend the time elsewhere."
                )
            )
            return Band(weight, because, names, note)
    raise ConcentrationError(f"no band for conviction {conviction!r}")  # pragma: no cover


def implied_conviction(weight_pct: float) -> dict[str, Any]:
    """Invert the policy: the conviction a position size is implicitly claiming.

    This is the direction worth running. A position is a statement about
    conviction whether or not anyone wrote the statement down, and comparing
    what your book claims against what your research supports is the one check
    that catches a thesis being quietly resized by enthusiasm.
    """
    w = float(weight_pct)
    if w < 0:
        raise ConcentrationError(f"weight cannot be negative: {weight_pct!r}")

    # Off the scale is checked before the search, so the band variables below
    # can never be read unbound.
    if w > BANDS[0][1]:
        return {
            "weight_pct": round(w, 3),
            "claims_at_least": None,
            "off_the_scale": True,
            "finding": (
                f"A {w:.1f}% position is above the {BANDS[0][1]:.0f}% ceiling this policy "
                "allows at any conviction. That is not a conviction claim any more, it is "
                "a concentration decision that has to be argued on its own terms."
            ),
        }

    # `BANDS` runs high-to-low, so the last band that still permits this weight
    # is the smallest one that fits — and its floor is the least conviction the
    # position could be claiming. Reporting that floor rather than a point
    # estimate is deliberate: the bands are wide, and a spurious "0.37" would
    # be exactly the false precision this module refuses everywhere else.
    claimed, band_max, band_because = min(
        ((floor, mx, why) for floor, mx, why in BANDS if w <= mx),
        key=lambda b: b[1],
    )

    return {
        "weight_pct": round(w, 3),
        "claims_at_least": claimed,
        "off_the_scale": False,
        "band_max_pct": band_max,
        "finding": (
            f"Holding {w:.1f}% claims conviction of at least {claimed:.2f}. {band_because}"
        ),
    }


def check_book(
    weights_pct: dict[str, float],
    *,
    stated: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compare what the book claims against what the research supports.

    ``weights_pct`` is ticker → percentage of the book. ``stated`` is the
    conviction actually computed for any of those names. Where both exist the
    two are compared and any position claiming more than its research supports
    is named — that gap is the finding, and it is the only output here that
    should change what anyone does today.
    """
    if not weights_pct:
        return {"positions": 0, "rows": [], "finding": "No positions to check."}

    rows: list[dict[str, Any]] = []
    overclaimed: list[str] = []
    for ticker, w in sorted(weights_pct.items(), key=lambda kv: -kv[1]):
        row = {"ticker": ticker, **implied_conviction(w)}
        if stated and ticker in stated:
            have = _clamp01(float(stated[ticker]))
            allowed = band_for(have).max_weight_pct
            row["stated_conviction"] = round(have, 4)
            row["allowed_weight_pct"] = allowed
            row["overclaimed"] = w > allowed
            if w > allowed:
                overclaimed.append(ticker)
                row["gap_note"] = (
                    f"Held at {w:.1f}% but the conviction chain scores {have:.2f}, which "
                    f"justifies {allowed:.0f}%. Either the research is understating the "
                    "case or the position is larger than the case supports."
                )
        rows.append(row)

    largest = rows[0]
    finding = (
        f"{len(overclaimed)} position(s) larger than their conviction supports: "
        + ", ".join(overclaimed)
        if overclaimed
        else (
            f"Every position sits inside the band its conviction allows. The largest, "
            f"{largest['ticker']} at {largest['weight_pct']:.1f}%, claims at least "
            f"{largest['claims_at_least']:.2f}."
            if largest.get("claims_at_least") is not None
            else f"{largest['ticker']} is above the policy ceiling — see its finding."
        )
    )

    return {
        "positions": len(rows),
        "rows": rows,
        "overclaimed": overclaimed,
        "finding": finding,
    }


def concentration(
    conviction: dict[str, Any],
    *,
    weights_pct: dict[str, float] | None = None,
) -> dict[str, Any]:
    """What this conviction permits, and whether the book already agrees.

    Takes the output of :func:`hedge_fund.valuation.conviction.conviction`
    directly. An unavailable chain produces an unavailable answer rather than a
    default size — the whole point of the chain refusing to score an unanswered
    requisite is lost if the next step quietly assumes zero and sizes anyway.
    """
    if not conviction.get("available"):
        return {
            "available": False,
            "reason": (
                "Conviction is unanswered, so there is no size to derive. An unanswered "
                "requisite is not a low score — sizing it as one would put money behind a "
                "question nobody has answered."
            ),
            "open_questions": conviction.get("open_questions", []),
        }

    score = float(conviction["score"])
    band = band_for(score)
    out: dict[str, Any] = {
        "available": True,
        "conviction": round(score, 4),
        "band": band.as_dict(),
        # Repeated from the chain on purpose: the weakest leg decides HOW the
        # view may be expressed and the band decides HOW MUCH. Showing the size
        # without the structure invites putting the full weight into the one
        # instrument the chain just ruled out.
        "structure": conviction.get("structure"),
    }
    if weights_pct:
        out["book"] = check_book(weights_pct)
    return out
