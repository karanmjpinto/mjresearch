"""Where a company sits in its capital cycle, read from its annual statements.

The capital-cycle school (Marathon, Hosking Partners) buys where capital is
leaving an industry and is wary where it is arriving: high returns attract
investment, the investment becomes supply, and the supply competes the returns
away. Hosking's Q3 2026 note applies it to memory — still selling, because the
profits are "super-normal" — while Cambrian's thesis buys memory for its
scarcity. This module makes the disagreement a number on every company.

Four signals, all from `data/statements.py`, each one an observable fact:

  capex over depreciation   above 1 the asset base is growing; well above,
                            supply is being built. Now, and three years ago.
  its direction             rising is capital arriving; falling, leaving.
  margin against its own    a margin far above the company's own average is
  average                   the profit that pulls capital in.
  share issuance            new equity is the clearest sign capital is
                            coming back (Hosking trimmed tankers for it).

The reading is one of `arriving`, `leaving` or `mixed`, from a count of the
signals each way. It is a description, not a forecast: capital can keep
arriving for years, and a margin can stay high if supply really cannot follow —
which is Cambrian's whole argument. The point is that the two theses are
visible side by side, not that one of them is resolved here.
"""

from __future__ import annotations

from typing import Any

#: Capex at or above this multiple of depreciation is building supply.
BUILDING = 1.5
#: At or below this the company is roughly replacing what wears out.
REPLACING = 1.1
#: A move in capex/depreciation this large over the window is a direction.
SHIFT = 0.3
#: Points above its own average at which a margin reads as the cycle's peak.
MARGIN_PEAK_PP = 10.0
#: Points below its own average at which a margin reads as the cycle's trough.
MARGIN_TROUGH_PP = 5.0
#: Annual share growth that reads as new equity coming in.
ISSUING_PCT = 2.0


def _ratio(capex: float | None, dep: float | None) -> float | None:
    if capex is None or dep is None or dep <= 0:
        return None
    return abs(capex) / dep


def read(table: dict[str, Any]) -> dict[str, Any] | None:
    """The capital-cycle reading for one statements table, or None if it cannot be read.

    Each signal is computed only from years that have it; a reading built on
    fewer than two of the four signals is not given.
    """
    if not isinstance(table, dict) or "error" in table:
        return None
    s = table.get("series") or {}
    capex, dep = s.get("capex") or [], s.get("depreciation") or []
    rev, op = s.get("revenue") or [], s.get("operating_income") or []
    shares = [x for x in (s.get("shares") or []) if x]

    ratios = [_ratio(c, d) for c, d in zip(capex, dep, strict=False)]
    now = ratios[0] if ratios else None
    # Three years back where the table reaches, else the oldest year it has.
    prior = next((r for r in reversed(ratios[1:4]) if r is not None), None)
    margins = [o / r * 100 for o, r in zip(op, rev, strict=False) if o is not None and r]
    margin_now = (op[0] / rev[0] * 100) if op and rev and op[0] is not None and rev[0] else None
    margin_gap = (
        (margin_now - sum(margins) / len(margins))
        if margin_now is not None and len(margins) >= 3
        else None
    )
    years = len(shares) - 1
    share_growth = ((shares[0] / shares[-1]) ** (1 / years) - 1) * 100 if years >= 1 else None

    arriving: list[str] = []
    leaving: list[str] = []
    if now is not None:
        if now >= BUILDING:
            arriving.append(f"capex {now:.1f}x depreciation")
        elif now <= REPLACING:
            leaving.append(f"capex {now:.1f}x depreciation")
    if now is not None and prior is not None:
        if now - prior >= SHIFT:
            arriving.append(f"capex rising from {prior:.1f}x")
        elif prior - now >= SHIFT:
            leaving.append(f"capex falling from {prior:.1f}x")
    if margin_gap is not None:
        if margin_gap >= MARGIN_PEAK_PP:
            arriving.append(f"margin {margin_gap:+.0f}pp above its average")
        elif margin_gap <= -MARGIN_TROUGH_PP:
            leaving.append(f"margin {margin_gap:+.0f}pp below its average")
    if share_growth is not None and share_growth >= ISSUING_PCT:
        arriving.append(f"shares growing {share_growth:.1f}% a year")

    measured = sum(x is not None for x in (now, margin_gap, share_growth)) + (
        now is not None and prior is not None
    )
    if measured < 2:
        return None
    if len(arriving) >= 2 and len(arriving) > len(leaving):
        verdict = "arriving"
    elif len(leaving) >= 2 and len(leaving) > len(arriving):
        verdict = "leaving"
    else:
        verdict = "mixed"
    return {
        "capital_cycle": verdict,
        "capex_to_depreciation": None if now is None else round(now, 2),
        "capex_to_depreciation_prior": None if prior is None else round(prior, 2),
        "margin_vs_average_pp": None if margin_gap is None else round(margin_gap, 1),
        "share_growth_pct_per_year": None if share_growth is None else round(share_growth, 2),
        "capital_cycle_evidence": "; ".join(
            arriving
            if verdict == "arriving"
            else leaving
            if verdict == "leaving"
            else arriving + leaving
        )
        or "no strong signal",
    }
