"""Where one company sits on the JKP themes, against a cross-section of peers.

JKP build each factor by sorting every stock on one characteristic and going
long one end and short the other. The honest single-name reading of that is a
rank: this company's value of the characteristic, placed among everyone else's.
So that is what this computes — a percentile per characteristic, flipped where
JKP go long the *low* end, so that above 50 always means "on the long side of
the factor as JKP built it".

Three limits, each of which the output states rather than hides:

**Only some characteristics are measurable here.** JKP compute 153 from CRSP
and Compustat. This app has the fundamentals and price fields the screen
caches hold, which cover a subset — and some of those are approximations (a
six-month return that does not skip the latest month, a five-year sales CAGR
standing in for three). Every characteristic carries its JKP id, and the
approximate ones say how they differ. A theme with nothing measurable is
returned as unmeasured, never as neutral: 50 would be a claim.

**The peers are the cached screen universes,** not JKP's full US sample. That
is ~500 S&P 500 names and ~600 S&P SmallCap names, with whichever fields each
screen fetched. The count behind every percentile is returned with it.

**A tilt is not a forecast.** Sitting on the long side of a factor that has
paid historically says what kind of company this is in the terms the factor
literature uses. It does not say the premium arrives for this name, this year.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hedge_fund.factors import jkp
from hedge_fund.screeners import cache as screen_cache

Flat = dict[str, Any]


def _num(flat: Flat, key: str) -> float | None:
    v = flat.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _ratio(num: float | None, den: float | None, *, positive_den: bool = True) -> float | None:
    if num is None or den is None or den == 0:
        return None
    if positive_den and den < 0:
        return None
    return num / den


def _first(*vals: float | None) -> float | None:
    return next((v for v in vals if v is not None), None)


@dataclass(frozen=True)
class Characteristic:
    #: The JKP characteristic id, so the row can be looked up on their site.
    id: str
    label: str
    formula: str
    compute: Callable[[Flat], float | None]
    #: How this differs from JKP's definition, when it does. None means the
    #: same quantity from a different data vendor.
    approximation: str | None = None


def _be_me(f: Flat) -> float | None:
    pb = _num(f, "price_to_book")
    return _first(
        1 / pb if pb and pb > 0 else None,
        _ratio(_num(f, "total_equity_mrq"), _num(f, "market_cap")),
    )


def _ebitda_mev(f: Flat) -> float | None:
    ev_ebitda = _num(f, "ev_to_ebitda")
    return _first(
        _ratio(_num(f, "ebitda_ttm"), _num(f, "enterprise_value")),
        1 / ev_ebitda if ev_ebitda else None,
    )


def _netdebt_me(f: Flat) -> float | None:
    nd_ebitda, ebitda = _num(f, "net_debt_to_ebitda"), _num(f, "ebitda_ttm")
    if nd_ebitda is None or ebitda is None:
        return None
    return _ratio(nd_ebitda * ebitda, _num(f, "market_cap"))


def _oaccruals_ni(f: Flat) -> float | None:
    ni, ocf = _num(f, "net_income_ttm"), _num(f, "operating_cash_flow_ttm")
    if ni is None or ocf is None or ni == 0:
        return None
    return (ni - ocf) / abs(ni)


def _ret_6_1(f: Flat) -> float | None:
    r = _num(f, "return_6m_pct")
    return r / 100 if r is not None else None


def _ret_1_0(f: Flat) -> float | None:
    r = _num(f, "return_1m_pct")
    return r / 100 if r is not None else None


CHARACTERISTICS: tuple[Characteristic, ...] = (
    # ── Value ───────────────────────────────────────────────────────────────
    Characteristic("be_me", "Book-to-market", "book equity ÷ market cap", _be_me),
    Characteristic(
        "ni_me",
        "Earnings-to-price",
        "net income (TTM) ÷ market cap",
        lambda f: _ratio(_num(f, "net_income_ttm"), _num(f, "market_cap")),
    ),
    Characteristic(
        "fcf_me",
        "Free cash flow-to-price",
        "free cash flow (TTM) ÷ market cap",
        lambda f: _ratio(
            _first(_num(f, "free_cash_flow_ttm"), _num(f, "fcf_ttm")), _num(f, "market_cap")
        ),
    ),
    Characteristic(
        "ocf_me",
        "Operating cash flow-to-market",
        "operating cash flow (TTM) ÷ market cap",
        lambda f: _ratio(_num(f, "operating_cash_flow_ttm"), _num(f, "market_cap")),
    ),
    Characteristic(
        "sale_me",
        "Sales-to-market",
        "revenue (TTM) ÷ market cap",
        lambda f: _ratio(_num(f, "revenue_ttm"), _num(f, "market_cap")),
    ),
    Characteristic("ebitda_mev", "EBITDA-to-EV", "EBITDA (TTM) ÷ enterprise value", _ebitda_mev),
    Characteristic(
        "chcsho_12m",
        "Net stock issues",
        "annual growth in shares outstanding",
        lambda f: _num(f, "share_cagr_5y"),
        approximation="Five-year average annual change in shares; JKP use the last twelve months.",
    ),
    # ── Size ────────────────────────────────────────────────────────────────
    Characteristic(
        "market_equity", "Market equity", "market capitalisation", lambda f: _num(f, "market_cap")
    ),
    # ── Momentum ────────────────────────────────────────────────────────────
    Characteristic(
        "ret_6_1",
        "Price momentum, 6 months",
        "price return over the last six months",
        _ret_6_1,
        approximation="Includes the latest month; JKP skip it (t−6 to t−1).",
    ),
    Characteristic(
        "prc_highprc_252d",
        "Price to 52-week high",
        "current price ÷ highest price in the last year",
        lambda f: _ratio(_num(f, "price_current"), _num(f, "price_52w_high")),
    ),
    # ── Short-term reversal ─────────────────────────────────────────────────
    Characteristic("ret_1_0", "Last month's return", "price return over the last month", _ret_1_0),
    # ── Profitability ───────────────────────────────────────────────────────
    Characteristic(
        "ni_be",
        "Return on equity",
        "net income (TTM) ÷ book equity",
        lambda f: _ratio(_num(f, "net_income_ttm"), _num(f, "total_equity_mrq")),
    ),
    Characteristic(
        "ebit_sale",
        "Profit margin",
        "operating income (TTM) ÷ revenue",
        lambda f: _first(
            _ratio(_num(f, "ebit_ttm"), _num(f, "revenue_ttm")), _num(f, "operating_margin_ttm")
        ),
    ),
    # ── Quality ─────────────────────────────────────────────────────────────
    Characteristic(
        "op_at",
        "Operating profit-to-assets",
        "operating income (TTM) ÷ total assets",
        lambda f: _ratio(_num(f, "operating_income_ttm"), _num(f, "total_assets_mrq")),
        approximation="Operating income; JKP deduct SG&A and R&D from gross profit.",
    ),
    # ── Investment ──────────────────────────────────────────────────────────
    Characteristic(
        "at_gr1",
        "Asset growth",
        "one-year growth in total assets",
        lambda f: _num(f, "yoy_total_assets_growth"),
    ),
    Characteristic(
        "sale_gr1",
        "Sales growth, 1 year",
        "one-year revenue growth",
        lambda f: _num(f, "revenue_yoy"),
    ),
    Characteristic(
        "sale_gr3",
        "Sales growth, multi-year",
        "annual revenue growth over five years",
        lambda f: _num(f, "revenue_cagr_5y"),
        approximation="Five-year CAGR; JKP use three-year growth.",
    ),
    # ── Low leverage ────────────────────────────────────────────────────────
    Characteristic(
        "at_be",
        "Book leverage",
        "total assets ÷ book equity",
        lambda f: _ratio(_num(f, "total_assets_mrq"), _num(f, "total_equity_mrq")),
    ),
    Characteristic("netdebt_me", "Net debt-to-price", "net debt ÷ market cap", _netdebt_me),
    # ── Accruals ────────────────────────────────────────────────────────────
    Characteristic(
        "oaccruals_ni",
        "Percent operating accruals",
        "(net income − operating cash flow) ÷ |net income|",
        _oaccruals_ni,
    ),
)


def _merge(results: list[dict[str, Any]], into: dict[str, Flat]) -> None:
    for row in results:
        t = row.get("ticker")
        snap = row.get("snapshot")
        if not t or not isinstance(snap, dict):
            continue
        # First writer wins per field; the caches agree on the fields they share
        # (they were fetched from the same provider), and keeping one value per
        # field stops a later cache silently changing an earlier rank.
        flat = into.setdefault(str(t).upper(), {})
        for k, v in snap.items():
            flat.setdefault(k, v)


def reference_universe() -> tuple[dict[str, Flat], list[dict[str, Any]]]:
    """Every cached name, with every field any screen fetched for it."""
    universe: dict[str, Flat] = {}
    sources = []
    for meta in screen_cache.available():
        got = screen_cache.read(meta["screen"], meta["universe"])
        if got is None:
            continue
        _merge(got.results, universe)
        sources.append(
            {
                "screen": got.screen,
                "universe": got.universe,
                "built_at": got.built_at,
                "count": len(got.results),
            }
        )
    return universe, sources


def percentile(value: float, sorted_ref: list[float]) -> float:
    """Mid-rank percentile, 0–100: ties share the middle of their run."""
    lo = bisect_left(sorted_ref, value)
    hi = bisect_right(sorted_ref, value)
    return 100 * (lo + hi) / (2 * len(sorted_ref))


#: A percentile over fewer peers than this is not reported. Twenty names put a
#: single rank step at five points, which is already coarse.
MIN_PEERS = 20


def profile(
    ticker: str,
    target: Flat | None = None,
    universe: dict[str, Flat] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Characteristic percentiles and theme tilts for one ticker.

    `target` overrides the ticker's cached fields — used when the name is not in
    any cache and its fields were fetched live. `universe` exists for tests.
    """
    ticker = ticker.upper()
    if universe is None:
        universe, sources = reference_universe()
    in_cache = ticker in universe
    flat = target if target is not None else universe.get(ticker, {})

    data = jkp.load()
    directions = {k: v["direction"] for k, v in data["factors"].items()}
    details = data["details"]["factors"]

    chars = []
    for c in CHARACTERISTICS:
        meta = details.get(c.id, {})
        row: dict[str, Any] = {
            "id": c.id,
            "label": c.label,
            "formula": c.formula,
            "approximation": c.approximation,
            "theme": meta.get("theme"),
            "jkp_name": meta.get("name"),
            "direction": directions.get(c.id, 1),
            "value": None,
            "percentile": None,
            "score": None,
            "peers": 0,
        }
        value = c.compute(flat) if flat else None
        ref = sorted(
            v for f in universe.values() if (v := c.compute(f)) is not None and math.isfinite(v)
        )
        row["peers"] = len(ref)
        if value is not None and math.isfinite(value) and len(ref) >= MIN_PEERS:
            pct = percentile(value, ref)
            row["value"] = value
            row["percentile"] = round(pct, 1)
            # Signed to JKP's long leg: above 50 is where their factor buys.
            row["score"] = round(pct if row["direction"] > 0 else 100 - pct, 1)
        elif value is not None and math.isfinite(value):
            row["value"] = value
        chars.append(row)

    themes = []
    theme_names = data["details"]["themes"]
    jkp_counts = {k: v["n_factors"] for k, v in data["themes"].items()}
    for tid in jkp.THEME_ORDER:
        mine = [r for r in chars if r["theme"] == tid]
        scored = [r["score"] for r in mine if r["score"] is not None]
        themes.append(
            {
                "id": tid,
                "name": theme_names.get(tid, tid),
                # Equal-weighted across what could be measured, the way JKP
                # build a theme from its factors. None, not 50, when nothing
                # was: an unmeasured theme is unknown, not neutral.
                "score": round(sum(scored) / len(scored), 1) if scored else None,
                "measured": len(scored),
                "measurable": len(mine),
                "jkp_factors": jkp_counts.get(tid),
            }
        )

    return {
        "ticker": ticker,
        "in_reference": in_cache,
        "source": "cache" if target is None else "live",
        "sector": flat.get("sector") if flat else None,
        "reference": {"names": len(universe), "caches": sources or []},
        "min_peers": MIN_PEERS,
        "characteristics": chars,
        "themes": themes,
    }
