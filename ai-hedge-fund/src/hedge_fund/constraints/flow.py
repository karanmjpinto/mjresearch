"""The constraint map as a flow: where the investable surface actually is.

A Sankey needs a quantity that conserves at every split. The constraint map has
no money in it — nothing in `config/constraints.json` carries a dollar figure,
and inventing one to make the picture prettier is the exact failure the file's
sourcing rule exists to prevent. What it does carry, and what does conserve, is
the count of **named exposures**: every listed company recorded against a
chokepoint, once per chokepoint it is named on.

So the flow is: all live exposures, split by system, split by chokepoint. The
width of a ribbon is how many ways there are to own that constraint, and each
terminal is divided by how pure those ways are — `pure`, `major`, `minor`, the
bands the catalogue already assigns.

WHY THIS IS WORTH DRAWING

Because the answer is counterintuitive and the card list hides it. Ordering each
system by how tight the constraint is puts the tightest at the top, and the
tightest ribbons are the *thinnest*: T-glass cloth is the second-tightest thing
on the map at 6.5x normal and has exactly one named company against it, a minor
exposure. Advanced packaging is the loosest at 1.15x and has five. The harder a
constraint is to get around, the fewer listed ways there are to own it — which
is a fact about market structure, and the kind of thing a chart can say in one
look and a list of cards cannot say at all.

The flow deliberately does not rank, score or recommend. It counts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hedge_fund.constraints.catalogue import Constraint, live

#: The order systems are drawn in, and the order they are listed everywhere
#: else in the app. Fixed so a system is always in the same place.
SYSTEM_ORDER = ("intelligence", "power", "motion")

#: Purest first. A terminal bar reads left to right in this order, so the
#: amount of `pure` on a chokepoint is always the leading segment.
BAND_ORDER = ("pure", "major", "minor")


def tightness(c: Constraint) -> float | None:
    """How far past normal the worst-measured leg sits, or None if unmeasured.

    `normal` is the same metric in an unconstrained market, so value/normal is
    a multiple with a meaning rather than an index. A constraint whose
    measurements carry no `normal` cannot be placed on this scale at all, and
    gets None rather than a default — the catalogue's whole posture is that an
    unanswered field stays unanswered.
    """
    ratios = [
        m.value / m.normal
        for m in c.measurements
        if m.normal is not None and m.normal != 0 and m.value is not None
    ]
    return max(ratios) if ratios else None


def _bands(c: Constraint) -> dict[str, int]:
    counts = dict.fromkeys(BAND_ORDER, 0)
    for n in c.names:
        if n.band in counts:
            counts[n.band] += 1
    return counts


def exposure_flow(path: Path | None = None) -> dict[str, Any]:
    """Named exposures flowing from the three systems out to each chokepoint.

    Every value in the result is a count of exposures, so the totals add up at
    each stage and the drawing cannot imply a magnitude nobody measured.
    """
    constraints = [c for c in live(path) if c.names]
    total = sum(len(c.names) for c in constraints)

    nodes: list[dict[str, Any]] = []
    for c in constraints:
        counts = _bands(c)
        nodes.append(
            {
                "id": c.id,
                "label": c.name,
                "system": c.system,
                "value": len(c.names),
                "tightness": tightness(c),
                "bands": counts,
                "share_pct": c.capture.get("share_pct"),
                "pricing_power": c.capture.get("pricing_power"),
            }
        )

    # Tightest first inside each system: the point of the chart is that ribbon
    # width tends to shrink as you read down, so the ordering carries it.
    def sort_key(n: dict[str, Any]) -> tuple[int, float]:
        t = n["tightness"]
        return (0, -t) if t is not None else (1, 0.0)

    systems = []
    for sid in SYSTEM_ORDER:
        members = sorted([n for n in nodes if n["system"] == sid], key=sort_key)
        if not members:
            continue
        systems.append(
            {
                "id": sid,
                "label": sid.capitalize(),
                "value": sum(n["value"] for n in members),
                "constraints": members,
            }
        )

    band_totals = [
        {
            "id": b,
            "label": b.capitalize(),
            "value": sum(n["bands"][b] for n in nodes),
        }
        for b in BAND_ORDER
    ]

    return {
        "unit": "named exposures",
        "total": total,
        "systems": systems,
        "bands": band_totals,
        "unmeasured": sorted(n["id"] for n in nodes if n["tightness"] is None),
        "note": (
            "Width is the number of listed companies named against a chokepoint, not "
            "money: nothing in the constraint map carries a dollar figure. Each system "
            "is ordered tightest first."
        ),
    }
