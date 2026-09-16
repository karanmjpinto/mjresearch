"""Valuation endpoints — comparable-company ranges for now, intrinsic value later."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from hedge_fund.data.service import get_data_service
from hedge_fund.valuation import implied_bands, summarise
from hedge_fund.valuation.concentration import concentration
from hedge_fund.valuation.cost_of_capital import COMPANY_TYPES, CostOfCapitalError, build
from hedge_fund.valuation.dcf import DCFError, Drivers, sensitivity, simulate, value
from hedge_fund.valuation.implied import implied_set
from hedge_fund.valuation.conviction import (
    EDGE_SOURCES,
    ConvictionError,
    conviction,
    correction_leg,
    fair_price_leg,
    horizon_leg,
)
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


@router.get("/conviction/{ticker}")
async def conviction_chain(
    ticker: str,
    edge_source: str | None = Query(
        None, description=f"Where the edge comes from: {', '.join(EDGE_SOURCES)}"
    ),
    margin_of_safety_pct: float | None = Query(
        None, description="Left blank, it is taken from the comparable range."
    ),
    verified_ratio: float | None = Query(None, ge=0.0, le=1.0),
    catalyst: str | None = Query(None),
    catalyst_certainty: float | None = Query(None, ge=0.0, le=1.0),
    finite_maturity: bool = Query(False),
    friction_explained: bool = Query(False),
    liquid: bool = Query(True),
    days_to_catalyst: float | None = Query(None, gt=0),
    holding_period_days: float | None = Query(None, gt=0),
    recent_wins: int = Query(0, ge=0),
) -> dict[str, Any]:
    """The three requisites, multiplied — and what the weakest one allows.

    Two of the three legs are judgments, so they are asked for rather than
    derived. Only the margin of safety is filled in automatically, and only
    because it is already computed next door.
    """
    t = ticker.strip().upper()

    mos = margin_of_safety_pct
    mos_source = "supplied"
    if mos is None:
        # The comparable range already knows the gap; no reason to ask twice.
        try:
            peers = _ds.get_peers(t)
            price = _last_close(t)
            if peers is not None and price:
                metrics = dict(getattr(peers, "metrics", {}) or {})
                bands, _ = implied_bands(
                    price, dict(metrics.get(t) or {}), {k: v for k, v in metrics.items() if k != t}
                )
                s = summarise(bands, price)
                if s.get("available") and s.get("mid"):
                    mos = round((1 - price / float(s["mid"])) * 100, 2)
                    mos_source = "from the comparable range"
        except Exception as exc:  # a missing gap is not a reason to fail the chain
            logger.debug("margin of safety lookup failed for %s: %s", t, exc)

    try:
        legs = [
            fair_price_leg(
                edge_source=edge_source,
                margin_of_safety_pct=mos,
                verified_ratio=verified_ratio,
            ),
            correction_leg(
                catalyst=catalyst,
                catalyst_certainty=catalyst_certainty,
                finite_maturity=finite_maturity,
                friction_explained=friction_explained,
                liquid=liquid,
            ),
            horizon_leg(
                days_to_catalyst=days_to_catalyst,
                holding_period_days=holding_period_days,
            ),
        ]
        result = conviction(legs, recent_wins=recent_wins)
    except ConvictionError as exc:
        raise HTTPException(422, str(exc)) from exc

    result["ticker"] = t
    result["margin_of_safety"] = {"value_pct": mos, "source": mos_source}
    result["edge_sources_available"] = list(EDGE_SOURCES)
    return result


def _book_weights() -> dict[str, float]:
    """Current holdings as a percentage of the book, or empty if unavailable.

    Best-effort on purpose. The concentration policy is useful without a book —
    it still says what a conviction permits — so a portfolio that cannot be
    priced costs the comparison and not the answer.
    """
    # parents[4], not [3]: this module sits two directories deeper than the
    # ones that read config with [3], and the first version of this silently
    # pointed at src/config, found nothing, and returned an empty book through
    # the handler below. A broad `except` around a path is how that stayed
    # invisible, so the miss is now logged loudly enough to notice.
    path = Path(__file__).resolve().parents[4] / "config" / "portfolio.json"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("no usable portfolio config at %s (%s); sizing without a book", path, exc)
        return {}

    book_ccy = str(cfg.get("currency", "")).strip().upper() or "USD"
    values: dict[str, float] = {}
    skipped: list[str] = []
    for h in cfg.get("holdings", []):
        tkr = str(h.get("ticker", "")).strip().upper()
        shares = _num(h.get("shares"))
        if not tkr or not shares:
            continue

        # Currency first, and this is not a nicety. There is no FX conversion
        # here, so a lira-priced holding multiplied by lira shares and summed
        # into a dollar book is not a small error — on the real portfolio it
        # made a Turkish airline 54% of the book and would have reported a
        # wildly over-concentrated position that does not exist. A holding in
        # another currency is excluded and named, never converted by guesswork.
        ccy = str(h.get("currency", book_ccy)).strip().upper() or book_ccy
        if ccy != book_ccy:
            skipped.append(f"{tkr} ({ccy})")
            continue

        price = _last_close(tkr)
        if price is None:
            skipped.append(f"{tkr} (no price)")
            continue
        values[tkr] = shares * price

    total = sum(values.values()) + (_num(cfg.get("cash")) or 0.0)
    if total <= 0:
        return {}
    if skipped:
        logger.info("book comparison excludes %s", ", ".join(skipped))
    weights = {k: round(v / total * 100, 4) for k, v in values.items()}
    # The excluded names ride along under a reserved key so the caller can say
    # the comparison is partial rather than quietly presenting it as the book.
    weights["__excluded__"] = skipped  # type: ignore[assignment]
    return weights


@router.get("/concentration/{ticker}")
async def concentration_policy(
    ticker: str,
    conviction_score: float | None = Query(
        None,
        ge=0.0,
        le=1.0,
        description="Left blank, the chain next door is not re-run — pass the score it produced.",
    ),
    against_book: bool = Query(
        True, description="Also check current holdings against the conviction each one claims."
    ),
) -> dict[str, Any]:
    """How big the view may be, and whether the book already agrees.

    Deliberately takes a score rather than recomputing the chain: the chain
    needs answers to two judgment questions, and silently re-deriving it here
    with defaults would produce a size from a thesis nobody stated.
    """
    t = ticker.strip().upper()

    if conviction_score is None:
        return {
            "ticker": t,
            "available": False,
            "reason": (
                "No conviction score supplied. Answer the three requisites next door "
                "first — a size derived from an unstated thesis is just a number."
            ),
            "book": None,
        }

    chain = {"available": True, "score": conviction_score, "structure": None}
    raw = _book_weights() if against_book else {}
    excluded = raw.pop("__excluded__", []) if raw else []
    weights = {k: float(v) for k, v in raw.items()}
    out = concentration(chain, weights_pct=weights or None)
    out["ticker"] = t
    if excluded:
        out["book_excluded"] = excluded
        out["book_excluded_note"] = (
            "Left out of the comparison because there is no FX conversion here: a holding "
            "priced in another currency cannot be summed into this book without inventing a "
            "rate. The weights shown are of the priced, same-currency part only."
        )
    if against_book and not weights:
        out["book_note"] = (
            "The book could not be priced, so there is nothing to compare against. "
            "Holdings in a currency the price feed did not return are left out rather "
            "than mixed into one weight."
        )
    return out


# ------------------------------------------------------------------
# What to put in the boxes
# ------------------------------------------------------------------

#: How to think about each driver, in the reader's language rather than the
#: model's. Written here rather than in the component so the explanation and
#: the arithmetic that needs it cannot drift apart.
#:
#: Each entry answers three questions in order: what the number is, what moves
#: it, and what would make it indefensible. The last one is the useful part —
#: knowing a margin cannot exceed what the industry has ever earned is worth
#: more than a definition.
DRIVER_HELP: dict[str, dict[str, str]] = {
    "revenue_growth": {
        "label": "Revenue growth",
        "what": "How fast sales grow each year, for the ten years the model forecasts.",
        "moves": (
            "Volume, price, and new markets. Past growth is the usual starting point, "
            "but a big company cannot keep a small company's rate — the base it grows "
            "from is larger every year."
        ),
        "bound": (
            "Nothing grows faster than its market forever. Compare against the implied "
            "figure below: that is the rate today's price is already paying for."
        ),
    },
    "target_operating_margin": {
        "label": "Target operating margin",
        "what": (
            "Operating profit as a share of sales, at the END of the forecast — not "
            "today's. The model walks from the current margin to this one."
        ),
        "moves": (
            "Scale, mix, and competition. Software drifts up as fixed costs spread; "
            "hardware and retail rarely do."
        ),
        "bound": (
            "The ceiling is what the best company in the industry has actually earned. "
            "A margin above anything the sector has ever posted is a claim that this "
            "business is a different kind of business."
        ),
    },
    "sales_to_capital": {
        "label": "Sales to capital",
        "what": (
            "Dollars of revenue each dollar of invested capital produces — so how "
            "much the growth above has to be paid for."
        ),
        "moves": (
            "Asset intensity. A fab or an airline sits near 1; a software or brand "
            "business can be 3 or more. Higher means growth is cheaper."
        ),
        "bound": (
            "Below about 0.5 growth consumes more cash than it brings in. The figure "
            "derived here is the company's own: revenue over debt plus book equity."
        ),
    },
    "terminal_growth": {
        "label": "Terminal growth",
        "what": "The rate assumed forever, after the forecast ends.",
        "moves": (
            "Almost nothing you control. It is a statement about the economy, not "
            "about the company."
        ),
        "bound": (
            "Hard ceiling: the risk-free rate. A business growing faster than that "
            "forever eventually becomes the whole economy, so the model refuses it."
        ),
    },
    "failure_probability": {
        "label": "Chance it fails",
        "what": (
            "The probability the business does not survive to deliver any of this, "
            "in which case the equity pays nothing."
        ),
        "moves": (
            "Debt load, cash burn, and whether it depends on refinancing. A profitable "
            "large-cap with net cash is near zero; a pre-revenue company carrying debt "
            "is not."
        ),
        "bound": (
            "No table is vendored here, so this is a judgment rather than a sourced "
            "figure — which is why it defaults to zero and says so rather than "
            "pretending to a number."
        ),
    },
}


@router.get("/driver-guidance/{ticker}")
async def driver_guidance(
    ticker: str, tax_rate: float = Query(0.25, ge=0.0, lt=1.0)
) -> dict[str, Any]:
    """For each driver: the company's own figure, and what the price implies.

    The second one is the point. Explaining what revenue growth *means* does
    not tell anyone whether 6% is bold or timid for this company; the rate
    already baked into the price does, because it converts a blank box into a
    position — above it you are the optimist, below it the sceptic.
    """
    t = ticker.strip().upper()
    f = _ds.get_fundamentals(t)
    if not f or f.get("error"):
        raise HTTPException(404, f"No fundamentals for {t}")

    price = _last_close(t)
    rf, rf_source = _live_riskfree()

    try:
        coc_build = build(
            beta=f.get("beta"),
            riskfree=rf,
            riskfree_source=rf_source if rf is not None else None,
            tax_rate=tax_rate,
            equity_value=f.get("market_cap"),
            debt_value=f.get("total_debt"),
        )
    except (ReferenceMissing, CostOfCapitalError) as exc:
        raise HTTPException(503, str(exc)) from exc

    coc = coc_build.wacc or coc_build.cost_of_equity
    derived, notes = _derive_drivers(f, price, coc)

    # The implied solve needs a complete driver set. Where a driver could not be
    # derived, a neutral stand-in is used *only* to hold the others steady while
    # solving — it is never reported as this company's figure.
    probe = Drivers(
        revenue=derived.get("revenue") or 0.0,
        revenue_growth=derived.get("revenue_growth") or 0.05,
        target_operating_margin=(
            derived.get("target_operating_margin") or derived.get("current_operating_margin") or 0.1
        ),
        current_operating_margin=derived.get("current_operating_margin"),
        sales_to_capital=derived.get("sales_to_capital") or 2.0,
        cost_of_capital=coc,
        tax_rate=tax_rate,
        terminal_growth=min(0.025, rf or 0.025),
        net_debt=derived.get("net_debt") or 0.0,
        shares=derived.get("shares") or 0.0,
        years=10,
    )

    implied: dict[str, Any] = {"drivers": {}, "note": ""}
    if price and probe.revenue > 0 and probe.shares > 0:
        try:
            implied = implied_set(probe, price, riskfree=rf)
        except Exception as exc:  # noqa: BLE001 - guidance must never 500
            logger.warning("implied solve failed for %s (%s)", t, exc)

    def own(key: str) -> float | None:
        v = derived.get(key)
        return round(float(v), 6) if isinstance(v, (int, float)) else None

    guidance = []
    for key, help_text in DRIVER_HELP.items():
        entry: dict[str, Any] = {"key": key, **help_text}
        if key == "terminal_growth":
            entry["yours"] = round(min(0.025, rf or 0.025), 6)
            entry["ceiling"] = round(rf, 6) if rf is not None else None
            entry["ceiling_source"] = rf_source
        elif key == "failure_probability":
            entry["yours"] = 0.0
            entry["sourced"] = False
        else:
            entry["yours"] = (
                own(key)
                if key != "target_operating_margin"
                else (own("target_operating_margin") or own("current_operating_margin"))
            )
        if key in implied.get("drivers", {}):
            entry["market_implied"] = implied["drivers"][key]
        guidance.append(entry)

    return {
        "ticker": t,
        "price": round(price, 2) if price else None,
        "sector": f.get("sector"),
        "industry": f.get("industry"),
        "cost_of_capital_pct": round(coc * 100, 3),
        "guidance": guidance,
        "implied_note": implied.get("note", ""),
        "derivation_notes": notes,
    }
