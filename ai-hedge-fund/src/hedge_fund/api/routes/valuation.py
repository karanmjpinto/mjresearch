"""Valuation endpoints — comparable-company ranges for now, intrinsic value later."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from hedge_fund.data.service import get_data_service
from hedge_fund.valuation import implied_bands, summarise
from hedge_fund.valuation.cost_of_capital import COMPANY_TYPES, CostOfCapitalError, build
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
