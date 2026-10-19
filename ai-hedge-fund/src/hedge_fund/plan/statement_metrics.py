"""Metrics over the annual statements in the snapshot.

Before these, the plan could see one year of ratios and a price chart, so it
could not answer "are margins holding up", "can it carry its debt" or "how much
of the return is buybacks" — sixteen of the thirty eval questions needed a
measure like these and none existed. Each reads `snapshot["statements"]`
(see `data/statements.py`) and nothing else, so a run stays reproducible from
its snapshot.

Two rules every metric here follows, because a statement table has holes:

- A year with a missing value is skipped for that measure, never treated as
  zero, and every metric reports how many years it actually used. A three-year
  growth rate and a one-year one are different claims and must read so.
- When a ratio's denominator is zero or negative — interest cover with no
  interest, leverage on negative EBITDA — the field is None with no guess
  behind it, and a metric with nothing left to say raises, so the plan shows
  the gap instead of a number.
"""

from __future__ import annotations

from typing import Any

from hedge_fund.plan.registry import _round, _snapshot_value, register
from hedge_fund.plan.types import FieldSpec, Metric, MetricError, ParamSpec


def _table(ctx: Any) -> dict[str, Any]:
    t = _snapshot_value(ctx, "statements")
    if not isinstance(t, dict) or "error" in t or not t.get("periods"):
        reason = t.get("error") if isinstance(t, dict) else "absent"
        raise MetricError(f"annual statements unavailable in the snapshot ({reason})")
    return t


def _s(t: dict[str, Any], sid: str) -> list[float | None]:
    return list((t.get("series") or {}).get(sid) or [])


def _pct(a: float | None, b: float | None) -> float | None:
    """a as a percentage of b, or None when b cannot divide."""
    if a is None or b is None or b <= 0:
        return None
    return a / b * 100


def _ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b <= 0:
        return None
    return a / b


def _latest(xs: list[float | None]) -> float | None:
    """The latest year's value, or None. Never an older year standing in: a
    ratio of this year's profit to a two-year-old interest bill is not a ratio."""
    return xs[0] if xs else None


# ----------------------------------------------------------------------
# revenue growth
# ----------------------------------------------------------------------


def _revenue_growth(ctx: Any, years: int) -> dict[str, Any]:
    t = _table(ctx)
    rev = _s(t, "revenue")
    # Newest first; the growth window is the newest `years` + 1 annual points.
    window = [r for r in rev[: years + 1]]
    known = [(i, r) for i, r in enumerate(window) if r is not None and r > 0]
    if len(known) < 2:
        raise MetricError("fewer than two years of revenue")
    (i0, newest), (i1, oldest) = known[0], known[-1]
    span = i1 - i0
    cagr = ((newest / oldest) ** (1 / span) - 1) * 100
    yoy = None
    if len(rev) > 1 and rev[0] and rev[1] and rev[1] > 0:
        yoy = (rev[0] / rev[1] - 1) * 100
    declines = sum(
        1 for a, b in zip(window, window[1:], strict=False) if a is not None and b and a < b
    )
    return {
        "revenue_latest": rev[0],
        "revenue_cagr_pct": _round(cagr, 2),
        "revenue_growth_latest_pct": _round(yoy, 2),
        "revenue_declining_years": declines,
        "revenue_years_used": span,
        "statement_currency": t.get("currency"),
    }


register(
    Metric(
        id="revenue_growth",
        label="Revenue growth",
        description="Compound annual revenue growth over several years, the latest year's growth, "
        "and how many years revenue fell.",
        tier="transform",
        params=(
            ParamSpec(
                "years", "integer", "Years of growth to measure.", default=3, minimum=1, maximum=5
            ),
        ),
        outputs=(
            FieldSpec(
                "revenue_latest",
                "number",
                "Revenue in the latest year, reporting currency",
                "currency",
            ),
            FieldSpec(
                "revenue_cagr_pct", "number", "Compound annual growth over the years used", "%"
            ),
            FieldSpec("revenue_growth_latest_pct", "number", "Growth in the latest year", "%"),
            FieldSpec(
                "revenue_declining_years", "integer", "Years in the window when revenue fell"
            ),
            FieldSpec("revenue_years_used", "integer", "Years of growth the CAGR actually spans"),
            FieldSpec("statement_currency", "string", "Currency the statements are reported in"),
        ),
        fn=_revenue_growth,
    )
)


# ----------------------------------------------------------------------
# margin trend
# ----------------------------------------------------------------------


def _margin_trend(ctx: Any) -> dict[str, Any]:
    t = _table(ctx)
    rev, gp, op, ni = (
        _s(t, k) for k in ("revenue", "gross_profit", "operating_income", "net_income")
    )
    op_m = [_pct(o, r) for o, r in zip(op, rev, strict=False)]
    gp_m = [_pct(g, r) for g, r in zip(gp, rev, strict=False)]
    known_op = [m for m in op_m if m is not None]
    if not known_op:
        raise MetricError("no year with both revenue and operating income")
    known_gp = [m for m in gp_m if m is not None]
    return {
        "gross_margin_pct": _round(_latest(gp_m), 2),
        "operating_margin_pct": _round(op_m[0], 2),
        "net_margin_pct": _round(_pct(_latest(ni), _latest(rev)), 2),
        "operating_margin_avg_pct": _round(sum(known_op) / len(known_op), 2),
        "operating_margin_change_pp": _round(known_op[0] - known_op[-1], 2)
        if len(known_op) > 1
        else None,
        "gross_margin_change_pp": _round(known_gp[0] - known_gp[-1], 2)
        if len(known_gp) > 1
        else None,
        "margin_years_used": len(known_op),
    }


register(
    Metric(
        id="margin_trend",
        label="Margin trend",
        description="Gross, operating and net margin in the latest year, and how the gross and "
        "operating margins have moved across the years reported.",
        tier="transform",
        outputs=(
            FieldSpec("gross_margin_pct", "number", "Gross profit over revenue, latest year", "%"),
            FieldSpec(
                "operating_margin_pct", "number", "Operating income over revenue, latest year", "%"
            ),
            FieldSpec("net_margin_pct", "number", "Net income over revenue, latest year", "%"),
            FieldSpec(
                "operating_margin_avg_pct",
                "number",
                "Average operating margin over the years used",
                "%",
            ),
            FieldSpec(
                "operating_margin_change_pp",
                "number",
                "Latest operating margin minus the earliest, in percentage points",
            ),
            FieldSpec(
                "gross_margin_change_pp",
                "number",
                "Latest gross margin minus the earliest, in percentage points",
            ),
            FieldSpec("margin_years_used", "integer", "Years with an operating margin"),
        ),
        fn=_margin_trend,
    )
)


# ----------------------------------------------------------------------
# cash conversion
# ----------------------------------------------------------------------


def _cash_conversion(ctx: Any) -> dict[str, Any]:
    t = _table(ctx)
    rev, ni, fcf, capex = (_s(t, k) for k in ("revenue", "net_income", "free_cash_flow", "capex"))
    if _latest(fcf) is None:
        raise MetricError("no free cash flow reported")
    # Summed over the years where both are known: one year's working-capital
    # swing makes a single-year ratio say almost anything.
    pairs = [(f, n) for f, n in zip(fcf, ni, strict=False) if f is not None and n is not None]
    conv = _ratio(sum(f for f, _ in pairs), sum(n for _, n in pairs)) if pairs else None
    return {
        "fcf_to_net_income": _round(conv, 3),
        "fcf_margin_pct": _round(_pct(_latest(fcf), _latest(rev)), 2),
        "capex_to_revenue_pct": _round(
            _pct(abs(c) if (c := _latest(capex)) is not None else None, _latest(rev)), 2
        ),
        "fcf_positive_years": sum(1 for f in fcf if f is not None and f > 0),
        "cash_years_used": len(pairs),
    }


register(
    Metric(
        id="cash_conversion",
        label="Cash conversion",
        description="Whether earnings turn into cash: free cash flow over net income across the "
        "years reported, the latest free-cash-flow margin, and capital intensity.",
        tier="transform",
        outputs=(
            FieldSpec(
                "fcf_to_net_income",
                "number",
                "Free cash flow over net income, summed across the years used; 1.0 is full conversion",
            ),
            FieldSpec("fcf_margin_pct", "number", "Free cash flow over revenue, latest year", "%"),
            FieldSpec(
                "capex_to_revenue_pct",
                "number",
                "Capital expenditure over revenue, latest year",
                "%",
            ),
            FieldSpec("fcf_positive_years", "integer", "Years with positive free cash flow"),
            FieldSpec(
                "cash_years_used", "integer", "Years with both free cash flow and net income"
            ),
        ),
        fn=_cash_conversion,
    )
)


# ----------------------------------------------------------------------
# balance sheet
# ----------------------------------------------------------------------


def _balance_sheet(ctx: Any) -> dict[str, Any]:
    t = _table(ctx)
    debt, cash = _latest(_s(t, "total_debt")), _latest(_s(t, "cash"))
    if debt is None and cash is None:
        raise MetricError("neither debt nor cash reported")
    net_debt = (debt or 0.0) - (cash or 0.0)
    ebitda, ebit = _latest(_s(t, "ebitda")), _latest(_s(t, "operating_income"))
    interest = _latest(_s(t, "interest_expense"))
    equity = _latest(_s(t, "equity"))
    return {
        "net_debt": net_debt,
        # Negative when net cash; None when EBITDA cannot divide.
        "net_debt_to_ebitda": _round(_ratio(net_debt, ebitda), 2),
        "interest_cover": _round(_ratio(ebit, abs(interest) if interest else None), 2),
        "debt_to_equity": _round(_ratio(debt, equity), 2),
        "net_cash": net_debt < 0,
        "statement_currency": t.get("currency"),
    }


register(
    Metric(
        id="balance_sheet",
        label="Balance sheet strength",
        description="Net debt, leverage against EBITDA, interest cover and debt to equity, from the "
        "latest balance sheet.",
        tier="transform",
        outputs=(
            FieldSpec(
                "net_debt",
                "number",
                "Debt less cash, reporting currency; negative is net cash",
                "currency",
            ),
            FieldSpec(
                "net_debt_to_ebitda",
                "number",
                "Net debt over EBITDA; negative means net cash. None when EBITDA is not positive",
            ),
            FieldSpec("interest_cover", "number", "Operating income over interest expense"),
            FieldSpec("debt_to_equity", "number", "Total debt over shareholders' equity"),
            FieldSpec("net_cash", "boolean", "Whether cash exceeds debt"),
            FieldSpec("statement_currency", "string", "Currency the statements are reported in"),
        ),
        fn=_balance_sheet,
    )
)


# ----------------------------------------------------------------------
# capital return
# ----------------------------------------------------------------------


def _capital_return(ctx: Any) -> dict[str, Any]:
    t = _table(ctx)
    shares = [s for s in _s(t, "shares") if s is not None and s > 0]
    bb, dv, fcf = (
        _latest(_s(t, "buybacks")),
        _latest(_s(t, "dividends")),
        _latest(_s(t, "free_cash_flow")),
    )
    if len(shares) < 2 and bb is None and dv is None:
        raise MetricError("no share count history and no buybacks or dividends reported")
    years = len(shares) - 1
    change = ((shares[0] / shares[-1]) ** (1 / years) - 1) * 100 if years >= 1 else None
    paid = abs(bb or 0.0) + abs(dv or 0.0)
    return {
        "share_count_change_pct_per_year": _round(change, 2),
        "buybacks_latest": abs(bb) if bb is not None else None,
        "dividends_latest": abs(dv) if dv is not None else None,
        "payout_to_fcf_pct": _round(_pct(paid, fcf), 1),
        "share_years_used": years,
    }


register(
    Metric(
        id="capital_return",
        label="Capital return",
        description="How much cash goes back to shareholders and what it does to the share count: "
        "annual change in shares, latest buybacks and dividends, and their total against free "
        "cash flow.",
        tier="transform",
        outputs=(
            FieldSpec(
                "share_count_change_pct_per_year",
                "number",
                "Annual change in split-adjusted shares; negative means shrinking",
                "%",
            ),
            FieldSpec(
                "buybacks_latest", "number", "Cash spent on buybacks in the latest year", "currency"
            ),
            FieldSpec(
                "dividends_latest",
                "number",
                "Cash paid as dividends in the latest year",
                "currency",
            ),
            FieldSpec(
                "payout_to_fcf_pct",
                "number",
                "Buybacks plus dividends over free cash flow, latest year; above 100 is borrowed or saved cash",
                "%",
            ),
            FieldSpec("share_years_used", "integer", "Years the share-count change spans"),
        ),
        fn=_capital_return,
    )
)


# ----------------------------------------------------------------------
# operating leverage
# ----------------------------------------------------------------------


def _operating_leverage(ctx: Any, sales_change_pct: float) -> dict[str, Any]:
    t = _table(ctx)
    rev, gp, op, dep = (
        _s(t, k) for k in ("revenue", "gross_profit", "operating_income", "depreciation")
    )
    ebit = _latest(op)
    if ebit is None:
        raise MetricError("no operating income reported")
    structural: float | None = None
    gross = _latest(gp)
    if ebit > 0 and gross is not None:
        # Depreciation and operating expense treated as fixed: contribution is
        # gross profit plus the depreciation inside cost of goods.
        structural = (gross + max(_latest(dep) or 0.0, 0.0)) / ebit
    observed: float | None = None
    r0, r1 = (rev + [None, None])[:2]
    o0, o1 = (op + [None, None])[:2]
    if r0 is not None and r1 and o0 is not None and o1 and o1 > 0:
        d_rev, d_op = r0 / r1 - 1, o0 / o1 - 1
        # Below a 1% sales move the ratio is noise divided by noise.
        if abs(d_rev) >= 0.01:
            observed = d_op / d_rev
    if structural is None and observed is None:
        raise MetricError("operating income is not positive, so leverage is undefined")
    return {
        "degree_of_operating_leverage": _round(structural, 2),
        "observed_operating_leverage": _round(observed, 2),
        "profit_change_for_sales_change_pct": _round(
            structural * sales_change_pct if structural is not None else None, 1
        ),
    }


register(
    Metric(
        id="operating_leverage",
        label="Operating leverage",
        description="How much operating profit moves when sales move: a structural estimate that "
        "treats depreciation and operating expense as fixed, last year's observed ratio, and the "
        "profit change implied for a given sales change.",
        tier="transform",
        params=(
            ParamSpec(
                "sales_change_pct",
                "number",
                "Sales change to translate into profit, in percent.",
                default=5.0,
                minimum=-50.0,
                maximum=100.0,
            ),
        ),
        outputs=(
            FieldSpec(
                "degree_of_operating_leverage",
                "number",
                "Contribution over operating income; 3 means profit moves three times as fast as sales",
            ),
            FieldSpec(
                "observed_operating_leverage",
                "number",
                "Last year's change in operating income over its change in revenue",
            ),
            FieldSpec(
                "profit_change_for_sales_change_pct",
                "number",
                "Operating profit change implied by the structural estimate for the given sales change",
                "%",
            ),
        ),
        notes="The structural figure overstates leverage where overheads flex with sales.",
        fn=_operating_leverage,
    )
)


# ----------------------------------------------------------------------
# capital cycle
# ----------------------------------------------------------------------


def _capital_cycle(ctx: Any) -> dict[str, Any]:
    from hedge_fund.data.capital_cycle import read

    out = read(_table(ctx))
    if out is None:
        raise MetricError("too few years of capex, margins or shares to read a capital cycle")
    return out


register(
    Metric(
        id="capital_cycle",
        label="Capital cycle",
        description="Whether capital is arriving in or leaving the business, the capital-cycle "
        "test: capex against depreciation now and three years ago, the margin against its own "
        "average, and share issuance. 'arriving' is the classic warning — high returns pulling in "
        "the supply that competes them away; 'leaving' is the classic opportunity.",
        tier="transform",
        outputs=(
            FieldSpec("capital_cycle", "string", "arriving, leaving or mixed"),
            FieldSpec(
                "capex_to_depreciation",
                "number",
                "Capex over depreciation, latest year; above 1 the asset base is growing",
            ),
            FieldSpec(
                "capex_to_depreciation_prior",
                "number",
                "Capex over depreciation about three years earlier",
            ),
            FieldSpec(
                "margin_vs_average_pp",
                "number",
                "Latest operating margin minus its average over the years reported, in points",
            ),
            FieldSpec(
                "share_growth_pct_per_year", "number", "Annual change in shares outstanding", "%"
            ),
            FieldSpec("capital_cycle_evidence", "string", "The signals behind the reading"),
        ),
        notes="A description of where capital is flowing, not a forecast of when it turns.",
        fn=_capital_cycle,
    )
)
