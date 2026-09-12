"""The cost of capital, built up rather than assumed.

One number decides more of a valuation than any other, and a single "discount
rate" typed into a cell is where most of the error lives. So it is assembled
from parts that can each be argued with separately:

    cost of equity = risk-free + beta x equity risk premium (+ country premium)
    cost of debt   = risk-free + the spread a company with this interest
                     coverage actually pays, after tax
    cost of capital = the two, weighted by what the company is financed with

Two rules hold throughout. Every input is echoed in the output, because a rate
whose derivation is invisible cannot be checked. And anything missing is named
and refused rather than defaulted: a plausible number from a guessed input is
worse than no number, since only the first one gets acted on.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hedge_fund.valuation.reference import Reference, load_reference

#: Which coverage table applies. Damodaran publishes three because the same
#: interest coverage means different things for a small company than for a
#: large one, and different again for a regulated utility.
COMPANY_TYPES = ("large_cap", "small_cap", "financial")


class CostOfCapitalError(ValueError):
    """An input was missing or unusable. The caller is told which."""


@dataclass
class Build:
    """A cost of capital and the whole derivation behind it."""

    cost_of_equity: float
    cost_of_debt_pre_tax: float | None
    cost_of_debt_after_tax: float | None
    wacc: float | None
    inputs: dict[str, Any] = field(default_factory=dict)
    steps: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        def pct(v: float | None) -> float | None:
            return None if v is None else round(v * 100, 3)

        return {
            "cost_of_equity_pct": pct(self.cost_of_equity),
            "cost_of_debt_pre_tax_pct": pct(self.cost_of_debt_pre_tax),
            "cost_of_debt_after_tax_pct": pct(self.cost_of_debt_after_tax),
            "wacc_pct": pct(self.wacc),
            "inputs": self.inputs,
            "steps": self.steps,
            "missing": self.missing,
        }


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def rating_for_coverage(coverage: float, table: list[Mapping[str, Any]]) -> tuple[str, float]:
    """The rating and default spread a given interest coverage implies.

    The bands are closed ranges, so the first one the coverage falls inside
    wins; anything above the top band takes the top band, which is how the
    published table is meant to be read.
    """
    if not table:
        raise CostOfCapitalError("no rating table available")
    for band in table:
        lo, hi = _num(band.get("coverage_from")), _num(band.get("coverage_to"))
        if lo is None or hi is None:
            continue
        if lo <= coverage <= hi:
            return str(band["rating"]), float(band["spread"])
    top = table[-1]
    return str(top["rating"]), float(top["spread"])


def blended_erp(
    exposure: Mapping[str, float] | None,
    ref: Reference,
) -> tuple[float, dict[str, Any]]:
    """Equity risk premium weighted by where revenue actually comes from.

    A company earning half its revenue in Turkey does not carry the US premium,
    and averaging the countries it operates in is the cheapest honest fix. An
    unrecognised country is refused by name rather than dropped, because
    silently dropping it understates risk — the one direction an error here
    must not go.
    """
    if not exposure:
        us = ref.country("united states")
        erp = (us.total_erp if us and us.total_erp else ref.implied_erp) or ref.implied_erp
        return erp, {"assumed": "100% United States", "erp": erp}

    total = sum(max(0.0, float(w)) for w in exposure.values())
    if total <= 0:
        raise CostOfCapitalError("revenue exposure weights sum to zero")

    unknown = [c for c in exposure if ref.country(c) is None]
    if unknown:
        raise CostOfCapitalError("no country risk data for: " + ", ".join(sorted(unknown)))

    detail: dict[str, Any] = {}
    blended = 0.0
    for name, weight in exposure.items():
        row = ref.country(name)
        assert row is not None  # guarded above
        erp = row.total_erp if row.total_erp is not None else ref.implied_erp
        share = max(0.0, float(weight)) / total
        blended += share * erp
        detail[row.name] = {"weight": round(share, 4), "total_erp": erp}
    return blended, {"weighted": detail, "erp": round(blended, 6)}


def build(
    *,
    beta: Any,
    riskfree: Any = None,
    riskfree_source: str | None = None,
    tax_rate: Any = 0.25,
    revenue_exposure: Mapping[str, float] | None = None,
    interest_coverage: Any = None,
    company_type: str = "large_cap",
    equity_value: Any = None,
    debt_value: Any = None,
    reference: Reference | None = None,
) -> Build:
    """Assemble the cost of capital from whatever is genuinely known."""
    ref = reference or load_reference()

    b = _num(beta)
    if b is None:
        raise CostOfCapitalError("beta is required and was not a usable number")
    if company_type not in COMPANY_TYPES:
        raise CostOfCapitalError(
            f"unknown company type {company_type!r}; expected one of {', '.join(COMPANY_TYPES)}"
        )

    rf = _num(riskfree)
    # The source travels with the rate. A build-up that shows 4.95% without
    # saying where it came from cannot be checked against anything.
    rf_source = riskfree_source or "supplied"
    if rf is None:
        rf, rf_source = ref.tbond_rate, f"10-year T-bond from the {ref.erp_as_of_year} dataset"

    erp, erp_detail = blended_erp(revenue_exposure, ref)
    ke = rf + b * erp

    steps = [
        f"risk-free {rf:.4f} ({rf_source})",
        f"equity risk premium {erp:.4f}",
        f"cost of equity = {rf:.4f} + {b:.3f} x {erp:.4f} = {ke:.4f}",
    ]
    missing: list[str] = []

    kd_pre = kd_post = wacc = None
    cov = _num(interest_coverage)
    tax = _num(tax_rate)
    if tax is None or not 0 <= tax < 1:
        raise CostOfCapitalError("tax rate must be a fraction between 0 and 1")

    rating = spread = None
    if cov is None:
        missing.append("interest coverage (EBIT / interest expense) — needed for the cost of debt")
    else:
        rating, spread = rating_for_coverage(cov, ref.rating_tables[company_type])
        kd_pre = rf + spread
        kd_post = kd_pre * (1 - tax)
        steps.append(f"coverage {cov:.2f}x implies {rating}, spread {spread:.4f}")
        steps.append(
            f"cost of debt after tax = ({rf:.4f} + {spread:.4f}) x (1 - {tax:.2f}) = {kd_post:.4f}"
        )

    e, d = _num(equity_value), _num(debt_value)
    if e is None or e <= 0:
        missing.append("market value of equity — needed to weight the two costs")
    elif d is None or d < 0:
        missing.append("total debt — needed to weight the two costs")
    elif kd_post is None:
        pass  # already reported: no cost of debt, so no weighting either
    else:
        total = e + d
        we, wd = e / total, d / total
        wacc = we * ke + wd * kd_post
        steps.append(
            f"cost of capital = {we:.3f} x {ke:.4f} + {wd:.3f} x {kd_post:.4f} = {wacc:.4f}"
        )

    return Build(
        cost_of_equity=ke,
        cost_of_debt_pre_tax=kd_pre,
        cost_of_debt_after_tax=kd_post,
        wacc=wacc,
        inputs={
            "beta": b,
            "riskfree": rf,
            "riskfree_source": rf_source,
            "equity_risk_premium": erp,
            "equity_risk_premium_detail": erp_detail,
            "tax_rate": tax,
            "interest_coverage": cov,
            "company_type": company_type,
            "synthetic_rating": rating,
            "default_spread": spread,
            "equity_value": e,
            "debt_value": d,
            "reference_as_of": ref.as_of(),
        },
        steps=steps,
        missing=missing,
    )
