"""A constraint, as three claims that must all hold.

The same shape as :mod:`hedge_fund.valuation.conviction`, and for the same
reason. A bottleneck is only investable if it is *binding* now, *and* it cannot
be routed around inside your horizon, *and* the company holding it actually
keeps the money. Score those separately and multiply, and one weak link caps
the result. Average them instead and a vivid story about a real shortage
carries a name whose customers capture every cent of the rent — which is the
most common way this kind of map loses money.

The three failures are different trades, not degrees of the same trade, which
is why the weakest leg selects an action:

* Not measurably tight yet → a watchlist item, not a position.
* Tight but easily designed around → a dated trade, not an investment.
* Tight and durable but the rent leaks → buy the beneficiary downstream.

Evidence is dated and decays. A lead time measured eighteen months ago is a
fact about eighteen months ago; treating it as a fact about now is how a map
keeps asserting a shortage that ended. An undated claim scores nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

#: How the chokepoint holder gets paid, which decides how "who keeps the rent"
#: can be answered at all.
#:
#: "concentration" is the normal case: a few firms hold the scarce thing and
#: their share gates whether they can price it.
#:
#: "market_price" is the case where concentration is the wrong question. When a
#: capacity auction sets one clearing price for every owner of an interconnected
#: megawatt, there is no holder whose share you could measure — the rent reaches
#: a diffuse set of owners through a published price. Asking for share there
#: would either block the leg forever or invite a made-up number, and the price
#: itself is better evidence than any share would be.
RENT_MECHANISMS = ("concentration", "market_price")

#: How a workaround stands. Ordered from "the constraint is safe" to
#: "the constraint is already dissolving".
ROUTE_STATUS = ("blocked", "unproven", "building", "open")

#: Months after which a measurement stops being evidence about the present.
#: Supply chains move on quarterly reporting cycles; two of those is the point
#: where "current" stops being honest and the claim needs re-checking.
STALE_MONTHS = 9.0

#: Months of announced new capacity beyond which a workaround is no longer a
#: threat to a normal holding period. Inside this, the fix is the thesis risk.
HORIZON_MONTHS = 36.0

#: What the weakest leg means for how the view may be expressed. This is the
#: rule that makes the chain operational rather than decorative.
STRUCTURE_RULE: dict[str | None, tuple[str, str]] = {
    # Reached only when the leg is *answered* and still weak, so the wording
    # must describe a measurement that came back unimpressive — not a missing
    # one. An unanswered leg never gets here: the chain reports itself
    # unavailable and lists the open questions instead.
    "binding": (
        "watchlist, not a position",
        "What is measured does not show it biting hard: the readings sit close "
        "to a normal market, or are old enough to describe the past rather than "
        "the present. Scarcity you cannot measure is a story about scarcity.",
    ),
    "durability": (
        "a dated trade, not an investment",
        "The workaround is credible and close. Own it for the squeeze and know "
        "when the new capacity lands, because that date is the thesis ending.",
    ),
    "capture": (
        "buy the beneficiary, not the chokepoint",
        "The shortage is real and the holder cannot price it. The rent is "
        "landing somewhere else in the chain — go and find who books it.",
    ),
    None: (
        "the constraint supports a position",
        "No leg is the clear weak point: it is tight, it is hard to route "
        "around, and the holder can price it.",
    ),
}


class ConstraintError(ValueError):
    """An input was unusable. The caller is told which."""


@dataclass
class Measurement:
    """One dated number that says whether the constraint is biting.

    ``normal`` is what the same metric reads in an unconstrained market. Without
    it a lead time is a number with no meaning — 52 weeks is alarming for a
    switchgear cabinet and unremarkable for a turbine — so a measurement with no
    baseline is kept and shown but cannot carry the leg.
    """

    metric: str
    value: float
    unit: str
    as_of: str  # ISO date
    source: str
    normal: float | None = None
    note: str = ""

    def months_old(self, today: date | None = None) -> float | None:
        try:
            when = date.fromisoformat(self.as_of)
        except (TypeError, ValueError):
            return None
        days = ((today or date.today()) - when).days
        return days / 30.44

    def tightness(self) -> float | None:
        """How far past normal this reading sits, as 0..1. None without a baseline."""
        if self.normal is None or self.normal <= 0 or self.value <= 0:
            return None
        # Double the normal lead time is treated as a full claim. Beyond that
        # the extra says the market is broken, not that it is twice as broken.
        return _clamp((self.value / self.normal - 1.0) / 1.0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "as_of": self.as_of,
            "source": self.source,
            "normal": self.normal,
            "note": self.note,
            "months_old": None if self.months_old() is None else round(self.months_old() or 0, 1),
            "tightness": self.tightness(),
        }


@dataclass
class Route:
    """A way the constraint could be designed, substituted or built around."""

    path: str
    status: str
    eta_months: float | None = None
    source: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status,
            "eta_months": self.eta_months,
            "source": self.source,
            "note": self.note,
        }


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


def _freshness(months: float | None) -> float:
    """Full weight while current, then straight-line to nothing at STALE_MONTHS."""
    if months is None:
        return 0.0
    if months <= 3.0:
        return 1.0
    if months >= STALE_MONTHS:
        return 0.0
    return _clamp((STALE_MONTHS - months) / (STALE_MONTHS - 3.0))


def binding_leg(measurements: list[Measurement]) -> Leg:
    """Requisite 1 — the constraint is the limiting factor, and it is now.

    Scored from the strongest *usable* reading rather than an average: one
    well-sourced current measurement of a sold-out line is worth more than four
    stale gestures, and averaging lets the stale ones dilute the live one.
    """
    open_q: list[str] = []
    usable: list[tuple[Measurement, float]] = []

    for m in measurements:
        age = m.months_old()
        tight = m.tightness()
        if age is None:
            open_q.append(f"{m.metric!r} carries no usable date — when was this measured?")
            continue
        if tight is None:
            open_q.append(
                f"What does {m.metric!r} read in a normal market? Without that it is a number, not a signal."
            )
            continue
        fresh = _freshness(age)
        if fresh == 0.0:
            open_q.append(
                f"{m.metric!r} is {age:.0f} months old — re-check it before trusting it as current."
            )
            continue
        usable.append((m, tight * fresh))

    if not usable:
        if not measurements:
            open_q.append(
                "What measures this constraint biting? A lead time, a utilisation rate, a backlog or a price."
            )
        return Leg(
            "binding",
            "It is binding now",
            "the limiting factor, measured",
            None,
            {"usable_measurements": 0},
            open_q,
        )

    best, score = max(usable, key=lambda pair: pair[1])
    return Leg(
        "binding",
        "It is binding now",
        "the limiting factor, measured",
        _clamp(score),
        {
            "usable_measurements": len(usable),
            "strongest": best.as_dict(),
            "freshness": round(_freshness(best.months_old()), 4),
        },
        open_q,
    )


def durability_leg(routes: list[Route]) -> Leg:
    """Requisite 2 — it cannot be routed around inside your horizon.

    An open workaround caps this hard however many blocked paths sit beside it:
    the chain breaks at its weakest point, and one credible substitute is a
    weak point no amount of other difficulty compensates for.
    """
    open_q: list[str] = []
    if not routes:
        open_q.append(
            "How could this be designed around, substituted, or built past? "
            "A constraint nobody has tried to route around has not been tested."
        )
        return Leg(
            "durability",
            "It cannot be routed around",
            "no credible substitute in horizon",
            None,
            {"routes": 0},
            open_q,
        )

    worst = 1.0
    detail_rows: list[dict[str, Any]] = []
    for r in routes:
        if r.status not in ROUTE_STATUS:
            raise ConstraintError(
                f"unknown route status {r.status!r}; expected one of {', '.join(ROUTE_STATUS)}"
            )
        if r.status == "open":
            # Already available. The constraint is not one.
            allowed = 0.1
        elif r.status == "building":
            eta = _num(r.eta_months)
            if eta is None:
                open_q.append(
                    f"When does {r.path!r} actually arrive? 'Building' without a date is not a risk you can size."
                )
                allowed = 0.4
            else:
                # Arriving tomorrow is nearly as bad as already here; beyond the
                # horizon it stops mattering to a normal holding period.
                allowed = _clamp(eta / HORIZON_MONTHS) * 0.9 + 0.1
        elif r.status == "unproven":
            allowed = 0.75
        else:  # blocked
            allowed = 1.0

        worst = min(worst, allowed)
        detail_rows.append(r.as_dict() | {"allows": round(allowed, 4)})

    binding_route = min(zip(routes, detail_rows, strict=True), key=lambda pair: pair[1]["allows"])[
        1
    ]
    return Leg(
        "durability",
        "It cannot be routed around",
        "no credible substitute in horizon",
        _clamp(worst),
        {"routes": len(routes), "paths": detail_rows, "closest_workaround": binding_route},
        open_q,
    )


def capture_leg(
    *,
    share_pct: Any = None,
    pricing_power: str | None = None,
    pricing_evidence: str = "",
    rent_mechanism: str = "concentration",
) -> Leg:
    """Requisite 3 — the holder of the chokepoint keeps the money.

    Share is necessary and nowhere near sufficient. A supplier can hold every
    unit of a scarce part and still ship it at last year's price because its
    customers are four times its size, or because a long-term contract fixed
    the number before anyone knew it was scarce. So pricing power is a stated,
    evidenced judgment and it gates the leg rather than nudging it.

    Under ``rent_mechanism="market_price"`` the concentration gate is dropped,
    because there is no holder to concentrate: a capacity auction pays every
    owner of a megawatt the same clearing price. The evidence requirement gets
    *stricter* rather than looser to compensate — without a stated receipt the
    leg stays unanswered, since price is the only thing carrying it.
    """
    if rent_mechanism not in RENT_MECHANISMS:
        raise ConstraintError(
            f"unknown rent_mechanism {rent_mechanism!r}; "
            f"expected one of {', '.join(RENT_MECHANISMS)}"
        )

    open_q: list[str] = []
    detail: dict[str, Any] = {
        "share_pct": _num(share_pct),
        "pricing_power": pricing_power,
        "rent_mechanism": rent_mechanism,
    }
    weights = {"demonstrated": 1.0, "contested": 0.5, "absent": 0.1}

    if pricing_power is None:
        open_q.append(
            "Has the holder actually raised prices or expanded margin on this? "
            "Answer 'demonstrated', 'contested' or 'absent' — scarcity alone is not pricing power."
        )
        return Leg(
            "capture", "The holder keeps the rent", "pricing power, evidenced", None, detail, open_q
        )
    if pricing_power not in weights:
        raise ConstraintError(
            f"unknown pricing_power {pricing_power!r}; expected one of {', '.join(weights)}"
        )

    if rent_mechanism == "market_price":
        if not pricing_evidence.strip():
            open_q.append(
                "What price proves it? With no holder to concentrate, the clearing price "
                "is the only evidence this leg has — name it, with its date and source."
            )
            return Leg(
                "capture",
                "The holder keeps the rent",
                "the market price is the receipt",
                None,
                detail,
                open_q,
            )
        detail |= {
            "pricing_component": weights[pricing_power],
            "pricing_evidence": pricing_evidence,
        }
        return Leg(
            "capture",
            "The holder keeps the rent",
            "the market price is the receipt",
            _clamp(weights[pricing_power]),
            detail,
            open_q,
        )

    share = _num(share_pct)
    if share is None:
        open_q.append("What share of this chokepoint does the holder actually control?")
        return Leg(
            "capture", "The holder keeps the rent", "pricing power, evidenced", None, detail, open_q
        )

    if pricing_power == "demonstrated" and not pricing_evidence.strip():
        open_q.append(
            "'Demonstrated' needs the evidence: which price rise, which quarter, which source?"
        )

    # Below a third of the chokepoint the holder is a participant, not a gate.
    concentration = _clamp((share - 30.0) / 50.0)
    score = concentration * weights[pricing_power]
    detail |= {
        "concentration_component": round(concentration, 4),
        "pricing_component": weights[pricing_power],
        "pricing_evidence": pricing_evidence,
    }
    return Leg(
        "capture",
        "The holder keeps the rent",
        "pricing power, evidenced",
        _clamp(score),
        detail,
        open_q,
    )


def validate(legs: list[Leg]) -> dict[str, Any]:
    """Multiply the legs, name the weakest, and say what it permits.

    An unanswered leg makes the whole chain unavailable and lists the open
    questions. A blank is not a zero and it is not a pass — an unvalidated
    constraint should read as unvalidated, not as a low score, because the two
    call for completely different next actions.
    """
    by_key = {leg.key: leg for leg in legs}
    for required in ("binding", "durability", "capture"):
        if required not in by_key:
            raise ConstraintError(f"missing requisite: {required}")

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
    action, why = STRUCTURE_RULE[weakest.key if (weakest.score or 0) < 0.5 else None]
    return {
        "available": True,
        "score": round(_clamp(raw), 4),
        "label": "strong" if raw >= 0.5 else "partial" if raw >= 0.2 else "weak",
        "weakest_leg": weakest.key,
        "structure": {"allowed": action, "because": why},
        "legs": [leg.as_dict() for leg in legs],
        "open_questions": [q for leg in legs for q in leg.open_questions],
    }
