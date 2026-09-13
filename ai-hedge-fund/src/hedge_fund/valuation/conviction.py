"""Conviction, as three claims that must all hold.

Damodaran's framing, and the reason this is a product rather than an average:
a position is only worth taking if your price is right, *and* the market
corrects towards it, *and* the correction arrives while you can still be
holding. Score those separately and multiply, and one weak link caps the
result. Add them up instead and a strong momentum reading carries a thesis
with no catalyst and no edge, which is the overreach the framework exists to
catch.

Everything here takes *stated* answers alongside computed evidence, because
two of the three legs are judgments and pretending otherwise would be the same
error in a new place. An unanswered leg scores nothing and the whole chain
reports itself unavailable, naming the question that is open. A blank is not a
zero and it is not a pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

#: Where an edge can legitimately come from. Anything else is not an edge.
EDGE_SOURCES = (
    "private_information",
    "information_processing",
    "business_understanding",
    "pricing_mistake",
)

#: What the weakest leg means for how the view may be expressed. This is the
#: rule that makes the chain operational rather than decorative.
STRUCTURE_RULE = {
    "fair_price": (
        "smaller size, or a pair against the sector",
        "If the edge is thin, stop betting on market direction as well and cut "
        "what a wrong valuation costs.",
    ),
    "correction": (
        "no trade — this is a value trap",
        "No catalyst, no maturity and no friction explaining the mispricing "
        "means cheap can stay cheap longer than you can stay solvent.",
    ),
    "horizon": (
        "shares, not options",
        "A share has no expiry, so waiting costs only time. An option puts a "
        "deadline on a view whose timing you just admitted you do not have.",
    ),
    None: (
        "the full band is available",
        "No leg is the clear weak point, so the size band stands as computed.",
    ),
}


class ConvictionError(ValueError):
    """An input was unusable. The caller is told which."""


@dataclass
class Leg:
    """One requisite: its score, what produced it, and what is still open."""

    key: str
    label: str
    claim: str
    score: float | None
    detail: dict[str, Any] = field(default_factory=dict)
    open_questions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "claim": self.claim,
            "score": None if self.score is None else round(self.score, 4),
            "detail": self.detail,
            "open_questions": self.open_questions,
        }


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def fair_price_leg(
    *,
    edge_source: str | None,
    margin_of_safety_pct: Any = None,
    verified_ratio: Any = None,
) -> Leg:
    """Requisite 1 — your fair price is right, or righter than the consensus.

    The edge source is a gate, not a weight: if none of the four can be named
    there is no reason to think your number beats the market's, whatever the
    gap looks like. Margin of safety then sizes the claim, and the share of
    narrated figures that survived checking discounts it.
    """
    open_q: list[str] = []
    detail: dict[str, Any] = {"edge_source": edge_source}

    if edge_source is None:
        open_q.append("Where does the edge come from? Name one of: " + ", ".join(EDGE_SOURCES))
        return Leg(
            "fair_price", "Fair price is right", "righter than consensus", None, detail, open_q
        )
    if edge_source not in EDGE_SOURCES:
        raise ConvictionError(
            f"unknown edge source {edge_source!r}; expected one of {', '.join(EDGE_SOURCES)}"
        )

    mos = _num(margin_of_safety_pct)
    if mos is None:
        open_q.append("How far below your value is the price? (margin of safety)")
        return Leg(
            "fair_price", "Fair price is right", "righter than consensus", None, detail, open_q
        )

    # A 40% discount is treated as a full claim; beyond that the extra does not
    # make you more right, it makes the estimate more suspect.
    gap = _clamp(mos / 40.0)
    evidence = _clamp(_num(verified_ratio) if verified_ratio is not None else 1.0)
    detail |= {
        "margin_of_safety_pct": mos,
        "gap_component": round(gap, 4),
        "evidence": round(evidence, 4),
    }
    if verified_ratio is None:
        detail["evidence_note"] = "no verification run; evidence taken at face value"
    return Leg(
        "fair_price",
        "Fair price is right",
        "righter than consensus",
        gap * evidence,
        detail,
        open_q,
    )


def correction_leg(
    *,
    catalyst: str | None,
    catalyst_certainty: Any = None,
    finite_maturity: bool = False,
    friction_explained: bool = False,
    liquid: bool = True,
) -> Leg:
    """Requisite 2 — the market will correct, and you can say why.

    A finite maturity forces convergence on its own, which is why a bond
    mispriced against its own maturity is a stronger claim than a stock
    mispriced against its fundamentals. Failing that you need a named catalyst;
    without one this is a value trap however cheap the thing looks.
    """
    open_q: list[str] = []
    detail: dict[str, Any] = {
        "catalyst": catalyst,
        "finite_maturity": bool(finite_maturity),
        "friction_explained": bool(friction_explained),
        "liquid": bool(liquid),
    }

    if not catalyst and not finite_maturity:
        open_q.append("What causes the correction? Name a catalyst, or a maturity that forces it.")
        return Leg("correction", "The market corrects", "and you can say why", None, detail, open_q)

    certainty = _num(catalyst_certainty)
    if finite_maturity and certainty is None:
        certainty = 0.9  # a maturity is a date, not an opinion
        detail["certainty_note"] = "a finite maturity forces convergence"
    if certainty is None:
        open_q.append("How certain is it that a correction comes? (0–1)")
        return Leg("correction", "The market corrects", "and you can say why", None, detail, open_q)

    score = _clamp(certainty)
    # Frictions explain why the price stayed wrong; illiquidity is why a
    # correction can fail to arrive even when everyone agrees it should.
    if friction_explained:
        score = _clamp(score * 1.1)
    if not liquid:
        score *= 0.7
        detail["liquidity_note"] = "thin trading can defer a correction indefinitely"
    detail["certainty"] = round(certainty, 4)
    return Leg("correction", "The market corrects", "and you can say why", score, detail, open_q)


def horizon_leg(*, days_to_catalyst: Any = None, holding_period_days: Any = None) -> Leg:
    """Requisite 3 — the correction lands inside your horizon.

    Being able to wait longer is itself an edge, so this is the ratio of what
    you can hold to what the correction needs, capped at one: waiting twice as
    long as necessary does not make the claim stronger.
    """
    open_q: list[str] = []
    d, h = _num(days_to_catalyst), _num(holding_period_days)
    detail: dict[str, Any] = {"days_to_catalyst": d, "holding_period_days": h}

    if d is None:
        open_q.append("How long until the correction? (days)")
    if h is None:
        open_q.append("How long can you hold? (days)")
    if d is None or h is None:
        return Leg(
            "horizon", "Inside your horizon", "before you have to sell", None, detail, open_q
        )
    if d <= 0:
        raise ConvictionError("days to catalyst must be positive")
    if h <= 0:
        raise ConvictionError("holding period must be positive")

    return Leg(
        "horizon",
        "Inside your horizon",
        "before you have to sell",
        _clamp(h / d),
        detail | {"ratio": round(h / d, 3)},
        open_q,
    )


def conviction(
    legs: list[Leg],
    *,
    recent_wins: int = 0,
    win_streak_threshold: int = 3,
) -> dict[str, Any]:
    """Multiply the legs, name the weakest, and discount for a hot streak.

    The humility check is the one place a number is deliberately reduced by
    something other than evidence. Credentials, self-confidence and above all a
    run of recent wins raise conviction without adding any, so a streak applies
    a haircut and says it did. A score that can only ever go up is a bug.
    """
    by_key = {leg.key: leg for leg in legs}
    for required in ("fair_price", "correction", "horizon"):
        if required not in by_key:
            raise ConvictionError(f"missing requisite: {required}")

    unanswered = [leg for leg in legs if leg.score is None]
    if unanswered:
        return {
            "available": False,
            "reason": "a requisite is unanswered, and a blank is not a zero",
            "open_questions": [q for leg in unanswered for q in leg.open_questions],
            "unanswered": [leg.key for leg in unanswered],
            "legs": [leg.as_dict() for leg in legs],
        }

    raw = 1.0
    for leg in legs:
        raw *= leg.score or 0.0

    weakest = min(legs, key=lambda leg: leg.score or 0.0)
    haircut = 0.0
    if recent_wins >= win_streak_threshold:
        # Enough to notice, not enough to pretend it is evidence of anything.
        haircut = min(0.25, 0.05 * (recent_wins - win_streak_threshold + 1))

    score = _clamp(raw * (1 - haircut))
    action, why = STRUCTURE_RULE[weakest.key if (weakest.score or 0) < 0.5 else None]
    return {
        "available": True,
        "score": round(score, 4),
        "raw_product": round(raw, 4),
        "label": "high" if score >= 0.5 else "moderate" if score >= 0.2 else "low",
        "weakest_leg": weakest.key,
        "structure": {"allowed": action, "because": why},
        "humility": {
            "recent_wins": recent_wins,
            "haircut": round(haircut, 4),
            "note": (
                f"{recent_wins} recent wins in a row — conviction cut by "
                f"{haircut:.0%}, because a streak raises confidence without adding evidence"
                if haircut
                else "no streak adjustment"
            ),
        },
        "legs": [leg.as_dict() for leg in legs],
    }
