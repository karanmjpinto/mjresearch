"""What comparable companies say a share is worth.

This is the other half of the comps work. Choosing the right companies
(`data/comps`) buys nothing until something converts their multiples into a
price you can set beside today's.

The arithmetic is deliberately dull. A multiple is a price divided by a
per-share quantity, so the subject's own multiple recovers that quantity
without opening the income statement: Apple at 332.27 on a P/E of 38.1 has
earnings of 8.72 a share, and a peer trading at 25x implies 218 for the same
earnings. Every number below is that one step, applied per multiple and per
percentile.

Two refusals matter more than the formula:

* A negative multiple is dropped, not used. A loss-making company has a
  negative P/E, and treating −12x as "cheaper than 8x" would rank losses as
  bargains. The drop is reported so a thin set is visible rather than silent.
* Fewer than `min_peers` usable values produces no band at all. A quartile
  drawn from two companies is decoration, and a football field is read as
  evidence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from statistics import median, quantiles
from typing import Any

#: Multiples we can invert into a per-share quantity, in display order.
MULTIPLES: tuple[tuple[str, str], ...] = (
    ("pe_ratio", "P/E"),
    ("forward_pe", "Forward P/E"),
    ("price_to_book", "P/B"),
)

#: Below this, a quartile is decoration rather than evidence.
MIN_PEERS = 3

#: How far the subject's own multiple may sit from the peer median before the
#: multiple stops comparing like with like. Apple trades near 45x book against
#: peers around 6x — not because it is expensive, but because buybacks have left
#: it almost no book equity, so price-to-book measures a different thing for the
#: subject than for the set. Including that row drags the range down by a factor
#: of four and produces a confident number about nothing. The band is still
#: returned, because hiding it would be its own kind of lie; it is marked
#: inapplicable and left out of the summary range.
OUTLIER_RATIO = 3.0


@dataclass(frozen=True)
class Band:
    """One multiple's implied value range for the subject."""

    metric: str
    label: str
    low: float
    mid: float
    high: float
    peer_count: int
    subject_multiple: float
    #: The per-share quantity recovered from the subject's own multiple —
    #: earnings for a P/E, book value for a P/B. Carried so the number is
    #: auditable rather than arriving from nowhere.
    per_share: float
    peer_low: float
    peer_mid: float
    peer_high: float
    #: False when the subject's own multiple is so far from the peer median
    #: that the two are not measuring the same thing.
    applicable: bool = True
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "label": self.label,
            "low": round(self.low, 2),
            "mid": round(self.mid, 2),
            "high": round(self.high, 2),
            "peer_count": self.peer_count,
            "subject_multiple": round(self.subject_multiple, 2),
            "per_share": round(self.per_share, 4),
            "peer_multiple": {
                "low": round(self.peer_low, 2),
                "mid": round(self.peer_mid, 2),
                "high": round(self.peer_high, 2),
            },
            "applicable": self.applicable,
            "note": self.note,
        }


@dataclass
class Dropped:
    """Why a multiple produced no band. A blank row needs a reason."""

    metric: str
    reason: str
    usable_peers: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"metric": self.metric, "reason": self.reason, "usable_peers": self.usable_peers}


def _positive(value: Any) -> float | None:
    """A multiple is usable only if it is a positive, finite number."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or f <= 0:
        return None
    return f


def _quartiles(values: list[float]) -> tuple[float, float, float]:
    """p25, p50, p75 with linear interpolation, matching the usual convention."""
    ordered = sorted(values)
    q = quantiles(ordered, n=4, method="inclusive")
    return q[0], median(ordered), q[2]


def implied_bands(
    price: float,
    subject: Mapping[str, Any],
    peers: Mapping[str, Mapping[str, Any]],
    *,
    min_peers: int = MIN_PEERS,
    multiples: tuple[tuple[str, str], ...] = MULTIPLES,
) -> tuple[list[Band], list[Dropped]]:
    """Implied value per share from each peer multiple.

    Returns the bands that could be computed and, separately, why the others
    could not — an empty football field with no explanation is indistinguishable
    from a broken one.
    """
    px = _positive(price)
    if px is None:
        return [], [Dropped(m, "no usable price for the subject") for m, _ in multiples]

    bands: list[Band] = []
    dropped: list[Dropped] = []

    for metric, label in multiples:
        own = _positive(subject.get(metric))
        if own is None:
            dropped.append(Dropped(metric, "the subject has no positive value for this multiple"))
            continue

        usable = [v for row in peers.values() if (v := _positive(row.get(metric))) is not None]
        if len(usable) < min_peers:
            dropped.append(
                Dropped(
                    metric,
                    f"only {len(usable)} peer(s) with a positive value; {min_peers} needed",
                    len(usable),
                )
            )
            continue

        per_share = px / own
        lo, mid, hi = _quartiles(usable)
        ratio = own / mid
        applicable = 1 / OUTLIER_RATIO <= ratio <= OUTLIER_RATIO
        note = (
            None
            if applicable
            else (
                f"the subject trades at {own:.1f}x against a peer median of {mid:.1f}x, "
                f"{ratio:.1f}x apart — this multiple is not comparing like with like here"
            )
        )
        bands.append(
            Band(
                metric=metric,
                label=label,
                low=lo * per_share,
                mid=mid * per_share,
                high=hi * per_share,
                peer_count=len(usable),
                subject_multiple=own,
                per_share=per_share,
                peer_low=lo,
                peer_mid=mid,
                peer_high=hi,
                applicable=applicable,
                note=note,
            )
        )

    return bands, dropped


def summarise(bands: list[Band], price: float) -> dict[str, Any]:
    """Where today's price sits against the bands.

    The range spans the lowest low to the highest high rather than averaging
    the bands: they disagree, and flattening that disagreement into one number
    is exactly what a football field exists to avoid.
    """
    px = _positive(price)
    if not bands or px is None:
        return {"available": False, "reason": "no bands could be computed"}

    usable = [b for b in bands if b.applicable]
    if not usable:
        return {
            "available": False,
            "reason": "every multiple was too far from the peer set to compare",
            "inapplicable": [b.metric for b in bands],
        }

    low = min(b.low for b in usable)
    high = max(b.high for b in usable)
    mid = median([b.mid for b in usable])
    position = "below the range" if px < low else "above the range" if px > high else "inside"
    return {
        "available": True,
        "low": round(low, 2),
        "mid": round(mid, 2),
        "high": round(high, 2),
        "price": round(px, 2),
        "position": position,
        "upside_to_mid_pct": round((mid / px - 1) * 100, 1),
        "methods": len(usable),
        "excluded": [b.metric for b in bands if not b.applicable],
    }
