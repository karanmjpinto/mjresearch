"""Valuation endpoints — comparable-company ranges for now, intrinsic value later."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from hedge_fund.data.service import get_data_service
from hedge_fund.valuation import implied_bands, summarise
from hedge_fund.valuation.cost_of_capital import COMPANY_TYPES, CostOfCapitalError, build
from hedge_fund.valuation.dcf import DCFError, Drivers, sensitivity, simulate, value
from hedge_fund.valuation.reference import ReferenceMissing

logger = logging.getLogger(__name__)
router = APIRouter()
_ds = get_data_service()


def _last_close(ticker: str) -> float | None:
    """Latest close. Short window: this is a spot price, not a series."""
    df = _ds.get_price_history(ticker, days=10)
    if df is None or getattr(df, "empty", True):
        return None
    for col in ("close", "Close"):
        if col in df.columns:
            series = df[col].dropna()
            if not series.empty:
                return float(series.iloc[-1])
    return None


@router.get("/comps/{ticker}")
async def comps_range(ticker: str) -> dict[str, Any]:
    """What the peer set says a share is worth, against today's price."""
    t = ticker.strip().upper()

    peers = _ds.get_peers(t)
    if peers is None:
        raise HTTPException(404, f"No peer data for {t}")

    metrics: dict[str, Any] = dict(getattr(peers, "metrics", {}) or {})
    subject = dict(metrics.get(t) or {})
    if not subject:
        # The peer path did not price the subject, so fall back to its own
        # fundamentals rather than returning an empty field with no reason.
        fundamentals = _ds.get_fundamentals(t)
        if not fundamentals.get("error"):
            subject = fundamentals

    peer_rows = {k: v for k, v in metrics.items() if k != t}
    price = _last_close(t)
    bands, dropped = implied_bands(price or 0.0, subject, peer_rows)

    return {
        "ticker": t,
        "price": round(price, 2) if price else None,
        "basis": getattr(peers, "basis", "unknown"),
        "vetted": bool(getattr(peers, "vetted", False)),
        "as_of": getattr(peers, "as_of", None),
        "peers": list(getattr(peers, "peers", []) or []),
        "bands": [b.as_dict() for b in bands],
        "dropped": [d.as_dict() for d in dropped],
        "summary": summarise(bands, price or 0.0),
    }


def _live_riskfree() -> tuple[float | None, str]:
    """The 10-year Treasury yield, live from FRED where it answers.

    Preferred over the rate baked into the vendored dataset because the
    risk-free rate is the one input that genuinely moves day to day. When FRED
    is unreachable the build-up falls back and says which it used, so the
    number is never ambiguous about its own source.
    """
    try:
        df = _ds.get_macro_data("DGS10", days=30)
        if df is None or getattr(df, "empty", True):
            return None, "unavailable"
        series = df.iloc[:, 0].dropna()
        if series.empty:
            return None, "unavailable"
        return float(series.iloc[-1]) / 100.0, "10-year Treasury (FRED DGS10, latest)"
    except Exception as exc:  # a macro outage must not fail a valuation
        logger.debug("FRED riskfree lookup failed: %s", exc)
        return None, "unavailable"


@router.get("/cost-of-capital/{ticker}")
async def cost_of_capital(
    ticker: str,
    interest_coverage: float | None = Query(
        None, description="EBIT / interest expense. Without it the cost of debt is not estimated."
    ),
    tax_rate: float = Query(0.25, ge=0.0, lt=1.0),
    company_type: str = Query("large_cap"),
) -> dict[str, Any]:
    """Cost of equity, of debt, and of capital — with every step shown."""
    t = ticker.strip().upper()
    if company_type not in COMPANY_TYPES:
        raise HTTPException(422, f"company_type must be one of {', '.join(COMPANY_TYPES)}")

    f = _ds.get_fundamentals(t)
    if f.get("error"):
        raise HTTPException(404, f"No fundamentals for {t}")

    rf, rf_source = _live_riskfree()

    try:
        result = build(
            beta=f.get("beta"),
            riskfree=rf,
            riskfree_source=rf_source if rf is not None else None,
            tax_rate=tax_rate,
            interest_coverage=interest_coverage,
            company_type=company_type,
            equity_value=f.get("market_cap"),
            debt_value=f.get("total_debt"),
        )
    except ReferenceMissing as exc:
        raise HTTPException(503, f"Reference data unavailable: {exc}") from exc
    except CostOfCapitalError as exc:
        raise HTTPException(422, str(exc)) from exc

    out = result.as_dict()
    out["ticker"] = t
    out["name"] = f.get("name")
    return out


def _derive_drivers(f: dict, price: float | None, coc: float) -> tuple[dict, list[str]]:
    """Work the drivers out of the filings where possible, and say where each came from.

    A driver whose origin is invisible cannot be argued with, so each carries a
    note. The two approximations are called out rather than buried: EBITDA
    stands in for operating profit where depreciation is not reported, which
    overstates the margin, and total debt stands in for net debt where cash is
    not reported, which understates the equity value. Both are conservative in
    opposite directions and both are better supplied by hand.
    """
    notes: list[str] = []
    revenue = _num(f.get("revenue"))
    ebitda = _num(f.get("ebitda"))
    debt = _num(f.get("total_debt")) or 0.0
    equity_book = _num(f.get("total_equity")) or 0.0
    mcap = _num(f.get("market_cap"))

    margin = None
    if revenue and ebitda:
        margin = ebitda / revenue
        notes.append("operating margin approximated from EBITDA, which overstates it")

    sales_to_capital = None
    invested = debt + equity_book
    if revenue and invested > 0:
        sales_to_capital = revenue / invested
        notes.append("sales-to-capital from revenue over debt plus book equity")

    shares = None
    if mcap and price:
        shares = mcap / price
        notes.append("share count implied by market value over price")

    if debt:
        notes.append("net debt taken as total debt; cash is not reported here, so this is cautious")

    return (
        {
            "revenue": revenue,
            "revenue_growth": _num(f.get("revenue_growth")),
            "current_operating_margin": margin,
            "sales_to_capital": sales_to_capital,
            "cost_of_capital": coc,
            "net_debt": debt,
            "shares": shares,
        },
        notes,
    )


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


@router.get("/intrinsic/{ticker}")
async def intrinsic(
    ticker: str,
    revenue_growth: float | None = Query(None, ge=-0.5, le=1.0),
    target_operating_margin: float | None = Query(None, gt=-1.0, lt=1.0),
    sales_to_capital: float | None = Query(None, gt=0),
    terminal_growth: float | None = Query(None, ge=0.0, le=0.1),
    tax_rate: float = Query(0.25, ge=0.0, lt=1.0),
    failure_probability: float = Query(0.0, ge=0.0, le=1.0),
    interest_coverage: float | None = Query(None),
    runs: int = Query(10_000, ge=100, le=50_000),
    years: int = Query(10, ge=1, le=20),
) -> dict[str, Any]:
    """Intrinsic value as a range, with the drivers and their sources shown."""
    t = ticker.strip().upper()
    f = _ds.get_fundamentals(t)
    if f.get("error"):
        raise HTTPException(404, f"No fundamentals for {t}")

    price = _last_close(t)
    rf, rf_source = _live_riskfree()

    # Cost of capital first: it is a driver, not a decoration.
    try:
        coc_build = build(
            beta=f.get("beta"),
            riskfree=rf,
            riskfree_source=rf_source if rf is not None else None,
            tax_rate=tax_rate,
            interest_coverage=interest_coverage,
            equity_value=f.get("market_cap"),
            debt_value=f.get("total_debt"),
        )
    except ReferenceMissing as exc:
        raise HTTPException(503, f"Reference data unavailable: {exc}") from exc
    except CostOfCapitalError as exc:
        raise HTTPException(422, str(exc)) from exc

    coc = coc_build.wacc or coc_build.cost_of_equity
    coc_note = (
        "cost of capital"
        if coc_build.wacc
        else "cost of equity used because the capital structure was incomplete"
    )

    derived, notes = _derive_drivers(f, price, coc)
    missing = [k for k, v in derived.items() if v is None]
    resolved = {
        **derived,
        "revenue_growth": revenue_growth
        if revenue_growth is not None
        else derived["revenue_growth"],
        "sales_to_capital": (
            sales_to_capital if sales_to_capital is not None else derived["sales_to_capital"]
        ),
    }
    resolved["target_operating_margin"] = (
        target_operating_margin
        if target_operating_margin is not None
        else resolved.get("current_operating_margin")
    )
    still_missing = [k for k, v in resolved.items() if v is None]
    if still_missing:
        return {
            "ticker": t,
            "available": False,
            "reason": "some drivers could not be worked out and were not supplied",
            "missing": still_missing,
            "supply": {k: f"pass ?{k}=" for k in still_missing if k != "shares"},
            "drivers": resolved,
            "notes": notes,
            "cost_of_capital": coc_build.as_dict(),
        }

    tg = terminal_growth if terminal_growth is not None else min(0.025, rf or 0.025)
    drivers = Drivers(
        revenue=resolved["revenue"],
        revenue_growth=resolved["revenue_growth"],
        target_operating_margin=resolved["target_operating_margin"],
        current_operating_margin=resolved["current_operating_margin"],
        sales_to_capital=resolved["sales_to_capital"],
        cost_of_capital=coc,
        tax_rate=tax_rate,
        terminal_growth=tg,
        failure_probability=failure_probability,
        net_debt=resolved["net_debt"] or 0.0,
        shares=resolved["shares"],
        years=years,
    )

    try:
        base = value(drivers, riskfree=rf)
        dist = simulate(drivers, price=price, runs=runs, riskfree=rf)
        grid = sensitivity(drivers, riskfree=rf)
    except DCFError as exc:
        raise HTTPException(422, str(exc)) from exc

    return {
        "ticker": t,
        "name": f.get("name"),
        "available": True,
        "price": round(price, 2) if price else None,
        "base_case": base.as_dict(),
        "distribution": dist,
        "sensitivity": grid,
        "cost_of_capital": coc_build.as_dict(),
        "cost_of_capital_note": coc_note,
        "driver_notes": notes,
        "derived_but_overridable": missing,
    }
