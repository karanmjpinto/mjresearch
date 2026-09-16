"""What today's price is already assuming.

The hardest part of a valuation is not the arithmetic, it is knowing whether 6%
revenue growth is a bold assumption or a timid one for this particular company.
No amount of explaining the *concept* of revenue growth answers that.

So this runs the model backwards. Hold every driver at its derived value, then
solve for the one that makes the DCF come out at exactly today's price. The
answer is what the market is currently paying for — and that is the anchor a
reader actually needs, because it converts a blank box into a position:

    implied growth 12%, and you think 6%   → you are bearish against the market
    implied growth 12%, and you think 18%  → you are the optimist here

Two things this deliberately is not.

It is not a forecast. The implied figure is a statement about the price, not
about the business, and it is only as good as the other drivers held fixed
around it — change the cost of capital and the implied growth moves without a
single fact about the company changing.

It is not always findable. Value is not monotonic in every driver over every
range, and some prices cannot be reached by moving one number alone: a company
trading at four times any defensible value has no implied growth rate, it has
a different story. Where the solve fails, this says so rather than returning
the edge of the search bracket, which would read as an answer.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Callable

from hedge_fund.valuation.dcf import DCFError, Drivers, value

logger = logging.getLogger(__name__)

#: Bisection is used rather than a derivative method because `value` is not
#: smooth — it clamps, it has a terminal-value discontinuity when growth
#: approaches the cost of capital, and it raises on invalid combinations.
#: Bisection only needs a sign change, which survives all three.
MAX_ITERATIONS = 60
#: Half a cent per share. Tighter than the price is ever quoted.
TOLERANCE = 0.005

#: Search brackets per driver, deliberately wider than anything defensible so
#: a real answer is not excluded, and finite so a failure is a failure.
BRACKETS: dict[str, tuple[float, float]] = {
    # -50% to +100% a year. Outside that the ten-year path is not a forecast.
    "revenue_growth": (-0.5, 1.0),
    # A loss-making business through to a software monopoly.
    "target_operating_margin": (-0.5, 0.9),
    # Growth costing four dollars of capital per dollar of sales, through to
    # almost nothing.
    "sales_to_capital": (0.25, 8.0),
}


def _solve(
    f: Callable[[float], float],
    lo: float,
    hi: float,
) -> float | None:
    """The x in [lo, hi] where f(x) = 0, by bisection, or None.

    `f` is allowed to raise: an invalid driver combination is a normal event
    here, not an error, and it simply means that end of the bracket is not
    usable. Returning None rather than the bracket edge is the whole point —
    a clamped answer looks exactly like a real one on screen.
    """

    def at(x: float) -> float | None:
        try:
            return f(x)
        except (DCFError, ValueError, ZeroDivisionError, OverflowError):
            return None

    f_lo, f_hi = at(lo), at(hi)

    # Walk the bracket inwards when an end is unusable, rather than giving up:
    # the extremes are where `value` is most likely to refuse, and the answer
    # is usually well inside.
    step = (hi - lo) / 20
    tries = 0
    while f_lo is None and tries < 10:
        lo += step
        f_lo = at(lo)
        tries += 1
    tries = 0
    while f_hi is None and tries < 10:
        hi -= step
        f_hi = at(hi)
        tries += 1

    if f_lo is None or f_hi is None or lo >= hi:
        return None
    # No sign change means the target is not inside the bracket at all. The
    # honest answer is "not reachable by moving this one number".
    if (f_lo > 0) == (f_hi > 0):
        return None

    for _ in range(MAX_ITERATIONS):
        mid = (lo + hi) / 2
        f_mid = at(mid)
        if f_mid is None:
            # A hole in the middle of the bracket. Bisection cannot step over
            # one, so stop rather than guess which side is real.
            return None
        if abs(f_mid) < TOLERANCE:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid

    return (lo + hi) / 2


def implied_driver(
    drivers: Drivers,
    driver: str,
    price: float,
    *,
    riskfree: float | None = None,
) -> float | None:
    """The value of one driver that makes the model agree with the price."""
    if driver not in BRACKETS:
        raise ValueError(f"no search bracket for {driver!r}")
    if not price or price <= 0:
        return None

    lo, hi = BRACKETS[driver]

    def gap(x: float) -> float:
        # `replace` rather than mutation: the caller's drivers are reused for
        # every other solve, and one mutated field would silently poison them.
        candidate = replace(drivers, **{driver: x})
        return value(candidate, riskfree=riskfree).value_per_share - price

    return _solve(gap, lo, hi)


def implied_set(
    drivers: Drivers,
    price: float,
    *,
    riskfree: float | None = None,
) -> dict[str, Any]:
    """Each driver's implied value, solved one at a time.

    One at a time, and the note says so. Solving them jointly has infinitely
    many answers — any growth rate can be made to fit by moving the margin —
    so each figure here is "what this driver would have to be if every other
    one is right", which is the only version of the question with one answer.
    """
    out: dict[str, Any] = {
        "price": round(price, 2),
        "note": (
            "Each figure is what that one driver would have to be for the model "
            "to agree with today's price, holding the others where they are. "
            "They are not a set that holds together at once."
        ),
        "drivers": {},
    }
    for name in BRACKETS:
        solved = implied_driver(drivers, name, price, riskfree=riskfree)
        out["drivers"][name] = None if solved is None else round(solved, 6)
        if solved is None:
            logger.debug("no implied %s for price %.2f", name, price)
    return out
