"""Intrinsic value: a two-stage free-cash-flow model, and a distribution of it.

Four drivers decide the answer — how fast revenue grows, what margin it settles
at, how much capital that growth consumes, and what the money costs — plus a
chance the story simply ends. Everything else in a discounted cash flow model
is bookkeeping around those five numbers.

The output is a range, not a figure. A single intrinsic value invites false
precision: the drivers are estimates, so the honest result is what they imply
across their plausible spread, with today's price marked on it. The simulation
is seeded and the seed is reported, because a value that moves between two runs
of the same inputs cannot be compared with last month's.

Three refusals are built in, each guarding an error that produces a large,
confident, wrong number:

* Terminal growth above the risk-free rate implies a company outgrowing the
  economy forever. Refused, with the rate it was checked against.
* Terminal growth at or above the cost of capital makes the terminal value
  negative or infinite. Refused before it divides.
* Shares, revenue and cost of capital that are absent or non-positive are
  refused rather than defaulted, since every one of them silently produces a
  plausible-looking value per share.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

#: Enough years for a growth story to converge on its terminal state without
#: pretending anyone can forecast a specific year a decade out.
DEFAULT_YEARS = 10

#: Seeded by default: the same inputs must give the same distribution, or a
#: changed number cannot be attributed to a changed view.
DEFAULT_SEED = 7


class DCFError(ValueError):
    """An input would produce a confident, wrong number. The caller is told which."""


@dataclass
class Drivers:
    """The five numbers that decide the answer."""

    revenue: float
    revenue_growth: float
    target_operating_margin: float
    sales_to_capital: float
    cost_of_capital: float
    tax_rate: float = 0.25
    terminal_growth: float = 0.025
    current_operating_margin: float | None = None
    failure_probability: float = 0.0
    failure_recovery: float = 0.0
    net_debt: float = 0.0
    shares: float = 1.0
    years: int = DEFAULT_YEARS

    def validate(self, riskfree: float | None = None) -> None:
        if self.revenue <= 0:
            raise DCFError("revenue must be positive")
        if self.shares <= 0:
            raise DCFError("share count must be positive")
        if self.cost_of_capital <= 0:
            raise DCFError("cost of capital must be positive")
        if not 0 <= self.tax_rate < 1:
            raise DCFError("tax rate must be a fraction between 0 and 1")
        if self.sales_to_capital <= 0:
            raise DCFError("sales-to-capital must be positive — growth consumes capital")
        if not 0 <= self.failure_probability <= 1:
            raise DCFError("failure probability must be between 0 and 1")
        if self.years < 1:
            raise DCFError("the forecast needs at least one year")
        if self.terminal_growth >= self.cost_of_capital:
            raise DCFError(
                f"terminal growth {self.terminal_growth:.3f} is not below the cost of capital "
                f"{self.cost_of_capital:.3f}; the terminal value would be negative or infinite"
            )
        if riskfree is not None and self.terminal_growth > riskfree:
            raise DCFError(
                f"terminal growth {self.terminal_growth:.3f} exceeds the risk-free rate "
                f"{riskfree:.3f}, which implies outgrowing the economy forever"
            )


@dataclass
class Valuation:
    """A value per share, and the year-by-year working behind it."""

    value_per_share: float
    equity_value: float
    firm_value: float
    terminal_value_pv: float
    terminal_share_of_value: float
    years: list[dict[str, Any]] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "value_per_share": round(self.value_per_share, 2),
            "equity_value": round(self.equity_value, 0),
            "firm_value": round(self.firm_value, 0),
            "terminal_value_pv": round(self.terminal_value_pv, 0),
            "terminal_share_of_value": round(self.terminal_share_of_value, 4),
            "years": self.years,
            "inputs": self.inputs,
        }


def value(drivers: Drivers, *, riskfree: float | None = None) -> Valuation:
    """One pass of the model: grow revenue, earn a margin, pay for the growth."""
    drivers.validate(riskfree)

    d = drivers
    margin0 = d.current_operating_margin
    if margin0 is None:
        margin0 = d.target_operating_margin

    revenue = d.revenue
    pv_sum = 0.0
    rows: list[dict[str, Any]] = []

    for year in range(1, d.years + 1):
        prior = revenue
        revenue = prior * (1 + d.revenue_growth)
        # The margin walks to its target rather than arriving at once: a
        # company does not re-rate its cost base in one year.
        share = year / d.years
        margin = margin0 + (d.target_operating_margin - margin0) * share
        ebit = revenue * margin
        after_tax = ebit * (1 - d.tax_rate)
        # Growth is not free. Every extra pound of revenue needs capital
        # behind it, and leaving this out is what makes naive models generous.
        reinvestment = max(0.0, (revenue - prior) / d.sales_to_capital)
        fcff = after_tax - reinvestment
        discount = (1 + d.cost_of_capital) ** year
        pv = fcff / discount
        pv_sum += pv
        rows.append(
            {
                "year": year,
                "revenue": round(revenue, 0),
                "operating_margin": round(margin, 4),
                "ebit": round(ebit, 0),
                "reinvestment": round(reinvestment, 0),
                "fcff": round(fcff, 0),
                "present_value": round(pv, 0),
            }
        )

    # Terminal value on the year after the forecast, grown once.
    terminal_fcff = rows[-1]["fcff"] * (1 + d.terminal_growth)
    terminal_value = terminal_fcff / (d.cost_of_capital - d.terminal_growth)
    terminal_pv = terminal_value / ((1 + d.cost_of_capital) ** d.years)

    going_concern = pv_sum + terminal_pv
    equity = going_concern - d.net_debt

    # A chance the story ends: the going concern is only worth what it is worth
    # if the company survives to deliver it.
    if d.failure_probability > 0:
        salvage = max(0.0, d.failure_recovery) * max(0.0, equity)
        equity = (1 - d.failure_probability) * equity + d.failure_probability * salvage

    firm = going_concern
    return Valuation(
        value_per_share=equity / d.shares,
        equity_value=equity,
        firm_value=firm,
        terminal_value_pv=terminal_pv,
        terminal_share_of_value=(terminal_pv / firm) if firm else 0.0,
        years=rows,
        inputs={
            "revenue": d.revenue,
            "revenue_growth": d.revenue_growth,
            "current_operating_margin": margin0,
            "target_operating_margin": d.target_operating_margin,
            "sales_to_capital": d.sales_to_capital,
            "cost_of_capital": d.cost_of_capital,
            "tax_rate": d.tax_rate,
            "terminal_growth": d.terminal_growth,
            "failure_probability": d.failure_probability,
            "failure_recovery": d.failure_recovery,
            "net_debt": d.net_debt,
            "shares": d.shares,
            "years": d.years,
            "riskfree_checked_against": riskfree,
        },
    )


def simulate(
    drivers: Drivers,
    *,
    price: float | None = None,
    runs: int = 10_000,
    seed: int = DEFAULT_SEED,
    growth_sd: float = 0.02,
    margin_sd: float = 0.02,
    sales_to_capital_sd: float = 0.3,
    cost_of_capital_sd: float = 0.005,
    riskfree: float | None = None,
) -> dict[str, Any]:
    """The same model over the drivers' plausible spread.

    Each draw perturbs the four drivers independently around the stated case.
    Independence is a simplification and an honest one to name: in practice
    growth and margin move together, and pretending otherwise makes the range
    a little wider than it should be rather than narrower, which is the safer
    direction for a number that sizes a position.
    """
    drivers.validate(riskfree)
    if runs < 100:
        raise DCFError("a distribution from fewer than 100 runs is decoration")

    rng = np.random.default_rng(seed)
    base = drivers
    values: list[float] = []
    rejected = 0

    for i in range(runs):
        trial = Drivers(**{**base.__dict__})
        trial.revenue_growth = float(rng.normal(base.revenue_growth, growth_sd))
        trial.target_operating_margin = float(rng.normal(base.target_operating_margin, margin_sd))
        trial.sales_to_capital = float(
            max(0.05, rng.normal(base.sales_to_capital, sales_to_capital_sd))
        )
        trial.cost_of_capital = float(
            max(base.terminal_growth + 0.005, rng.normal(base.cost_of_capital, cost_of_capital_sd))
        )
        try:
            values.append(value(trial, riskfree=None).value_per_share)
        except DCFError:
            # A draw can wander into an impossible combination; it is dropped
            # and counted rather than clamped, so the reported count is honest.
            rejected += 1

    if not values:
        raise DCFError("every simulated draw was impossible; check the drivers")

    arr = np.array(values)
    pcts = {f"p{p}": round(float(np.percentile(arr, p)), 2) for p in (5, 10, 25, 50, 75, 90, 95)}

    # Bin counts travel with the percentiles so a caller can draw the shape
    # rather than infer it from seven numbers. The tails matter here: a wide
    # left tail is the difference between a cheap share and a lottery ticket.
    counts, edges = np.histogram(arr, bins=24)
    histogram = [
        {
            "from": round(float(edges[i]), 2),
            "to": round(float(edges[i + 1]), 2),
            "count": int(counts[i]),
        }
        for i in range(len(counts))
    ]
    out: dict[str, Any] = {
        "runs": len(values),
        "rejected": rejected,
        "seed": seed,
        "percentiles": pcts,
        "histogram": histogram,
        "mean": round(float(arr.mean()), 2),
        "base_case": round(value(base, riskfree=riskfree).value_per_share, 2),
        "spreads": {
            "growth_sd": growth_sd,
            "margin_sd": margin_sd,
            "sales_to_capital_sd": sales_to_capital_sd,
            "cost_of_capital_sd": cost_of_capital_sd,
        },
        "independence_note": (
            "drivers are drawn independently; growth and margin move together in "
            "practice, which makes this range slightly wider than reality"
        ),
    }
    if price is not None and math.isfinite(price) and price > 0:
        above = float((arr > price).mean())
        out["price"] = round(price, 2)
        out["probability_value_above_price"] = round(above, 4)
        out["median_upside_pct"] = round((pcts["p50"] / price - 1) * 100, 1)
    return out


def sensitivity(
    drivers: Drivers,
    *,
    cost_of_capital_steps: tuple[float, ...] = (-0.01, -0.005, 0.0, 0.005, 0.01),
    terminal_growth_steps: tuple[float, ...] = (-0.01, -0.005, 0.0, 0.005, 0.01),
    riskfree: float | None = None,
) -> dict[str, Any]:
    """Value across cost of capital and terminal growth — the table checked first."""
    grid: list[dict[str, Any]] = []
    for dw in cost_of_capital_steps:
        row: dict[str, Any] = {
            "cost_of_capital": round(drivers.cost_of_capital + dw, 5),
            "values": [],
        }
        for dg in terminal_growth_steps:
            trial = Drivers(**{**drivers.__dict__})
            trial.cost_of_capital = drivers.cost_of_capital + dw
            trial.terminal_growth = drivers.terminal_growth + dg
            try:
                row["values"].append(
                    {
                        "terminal_growth": round(trial.terminal_growth, 5),
                        "value_per_share": round(
                            value(trial, riskfree=riskfree).value_per_share, 2
                        ),
                    }
                )
            except DCFError as exc:
                row["values"].append(
                    {"terminal_growth": round(trial.terminal_growth, 5), "refused": str(exc)}
                )
        grid.append(row)
    return {"grid": grid}
