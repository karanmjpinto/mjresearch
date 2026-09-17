"""
Yartseva Multibagger screener — Stage 1 filters, Stage 2 scoring, short-sell flag.

Data via yfinance (quarterly TTM sums, profile fields). Not investment advice.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# --- Constants (USD) ---
MCAP_MIN = 50_000_000
MCAP_MAX = 2_000_000_000
EXCLUDED_SECTORS = frozenset(
    {
        "Financial Services",
        "Financials",
        "Utilities",
    }
)


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if pd.isna(v):
        return None
    return v


def _sum_q(df: pd.DataFrame | None, row: str, start: int, end: int) -> float | None:
    if df is None or df.empty or row not in df.index:
        return None
    r = df.loc[row]
    if len(r) < end:
        return None
    chunk = r.iloc[start:end]
    return float(pd.to_numeric(chunk, errors="coerce").fillna(0).sum())


def _annual_yoy(df: pd.DataFrame | None, row: str) -> float | None:
    """Year-over-year growth in percent from the two most recent fiscal years.

    Exists because the prior-year TTM cannot be summed from quarterly data.
    `_sum_q` needs all eight quarters and refuses a short window — correctly,
    since a three-quarter "TTM" understates — but yfinance returns four to
    seven quarters, so the prior TTM was `None` for every company ever
    screened. EBITDA growth was therefore always unknown, which made the
    investment-quality penalty always zero: a designed check that had never
    once fired, on a screen that reported its scores as if it had.

    The annual statement goes back four years, so the comparison is made
    there instead. Both sides are full fiscal years, which is the part that
    matters — a TTM measured against an annual figure would fold up to three
    quarters of drift into the growth rate.
    """
    if df is None or df.empty or row not in df.index:
        return None
    r = pd.to_numeric(df.loc[row], errors="coerce").dropna()
    if len(r) < 2:
        return None
    cur, prev = float(r.iloc[0]), float(r.iloc[1])
    if abs(prev) < 1e-6:
        return None
    return (cur - prev) / abs(prev) * 100


@dataclass
class YartsevaSnapshot:
    ticker: str
    market_cap: float | None = None
    enterprise_value: float | None = None
    sector: str | None = None
    total_equity_mrq: float | None = None
    total_assets_mrq: float | None = None
    total_assets_prior_yoy: float | None = None
    revenue_ttm: float | None = None
    ebitda_ttm: float | None = None
    ebitda_prior_ttm: float | None = None
    #: Fiscal-year EBITDA growth, used when the prior TTM cannot be summed.
    ebitda_growth_pct_annual: float | None = None
    operating_income_ttm: float | None = None
    net_income_ttm: float | None = None
    free_cash_flow_ttm: float | None = None
    operating_margin_ttm: float | None = None
    price_current: float | None = None
    price_52w_high: float | None = None
    price_52w_low: float | None = None
    return_6m_pct: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    ps_ratio: float | None = None
    yoy_total_assets_growth: float | None = None
    error: str | None = None


def fetch_yartseva_snapshot(ticker: str) -> YartsevaSnapshot:
    """Pull fields required for Yartseva scoring from yfinance."""
    t = yf.Ticker(ticker.strip().upper())
    snap = YartsevaSnapshot(ticker=ticker.strip().upper())
    try:
        info = t.info or {}
        if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
            snap.error = "no_quote_or_info"
            return snap

        snap.market_cap = _f(info.get("marketCap"))
        snap.enterprise_value = _f(info.get("enterpriseValue"))
        snap.sector = info.get("sector") or info.get("industry") or None
        snap.price_current = _f(info.get("currentPrice") or info.get("regularMarketPrice"))
        snap.price_52w_high = _f(info.get("fiftyTwoWeekHigh"))
        snap.price_52w_low = _f(info.get("fiftyTwoWeekLow"))
        snap.forward_pe = _f(info.get("forwardPE"))
        snap.peg_ratio = _f(info.get("pegRatio"))

        q_inc = t.quarterly_income_stmt
        a_inc = t.income_stmt
        q_bs = t.quarterly_balance_sheet
        q_cf = t.quarterly_cashflow

        # TTM = last 4 quarters; prior TTM = quarters 4–8
        rev_ttm = _sum_q(q_inc, "Total Revenue", 0, 4)
        oi_ttm = _sum_q(q_inc, "Operating Income", 0, 4)
        ebitda_ttm = _sum_q(q_inc, "EBITDA", 0, 4)
        ni_ttm = _sum_q(q_inc, "Net Income", 0, 4)
        ebitda_prior = _sum_q(q_inc, "EBITDA", 4, 8)

        # Quarterly first; the annual statement is the fallback that actually
        # fires, since yfinance rarely returns the eight quarters needed.
        snap.ebitda_growth_pct_annual = _annual_yoy(a_inc, "EBITDA")

        snap.revenue_ttm = rev_ttm
        snap.ebitda_ttm = ebitda_ttm
        snap.ebitda_prior_ttm = ebitda_prior
        snap.operating_income_ttm = oi_ttm
        snap.net_income_ttm = ni_ttm

        if rev_ttm and rev_ttm > 0 and oi_ttm is not None:
            snap.operating_margin_ttm = oi_ttm / rev_ttm
        else:
            snap.operating_margin_ttm = None

        fcf_ttm = _sum_q(q_cf, "Free Cash Flow", 0, 4)
        snap.free_cash_flow_ttm = fcf_ttm

        teq = None
        if q_bs is not None and not q_bs.empty:
            for row in (
                "Stockholders Equity",
                "Total Equity Gross Minority Interest",
                "Common Stock Equity",
            ):
                if row in q_bs.index:
                    teq = _f(q_bs.loc[row].iloc[0])
                    break
            ta0 = _f(q_bs.loc["Total Assets"].iloc[0]) if "Total Assets" in q_bs.index else None
            ta4 = (
                _f(q_bs.loc["Total Assets"].iloc[4])
                if "Total Assets" in q_bs.index and len(q_bs.columns) > 4
                else None
            )
            snap.total_assets_mrq = ta0
            snap.total_equity_mrq = teq
            snap.total_assets_prior_yoy = ta4
            if ta0 is not None and ta4 is not None and ta4 != 0:
                snap.yoy_total_assets_growth = (ta0 - ta4) / ta4

        if snap.market_cap and rev_ttm and rev_ttm > 0:
            snap.ps_ratio = snap.market_cap / rev_ttm

        hist = pd.DataFrame()
        try:
            hist = t.history(period="400d", interval="1d")
        except Exception as exc:
            # The candidate is still scored, on fundamentals alone. Say so:
            # a screen result computed without price history is not the same
            # result, and nothing downstream can tell the difference.
            logger.warning("%s: no price history (%s); scoring without it", snap.ticker, exc)
        # 6m return from daily history
        if not hist.empty and "Close" in hist.columns and snap.price_current:
            close = hist["Close"].dropna()
            if len(close) >= 2:
                i6 = max(0, len(close) - 126)
                p0 = float(close.iloc[-1])
                p6 = float(close.iloc[i6])
                if p6 > 0:
                    snap.return_6m_pct = (p0 - p6) / p6 * 100

        # Fallback 52w range from history if missing
        if (snap.price_52w_high is None or snap.price_52w_low is None) and not hist.empty:
            snap.price_52w_high = snap.price_52w_high or float(hist["High"].max())
            snap.price_52w_low = snap.price_52w_low or float(hist["Low"].min())

    except Exception as e:
        logger.warning("yartseva fetch failed for %s: %s", ticker, e)
        snap.error = str(e)
    return snap


def _score_fcf_yield_pct(pct: float) -> float:
    if pct > 15:
        return 100.0
    if pct > 10:
        return 80.0
    if pct > 7:
        return 60.0
    if pct > 4:
        return 40.0
    if pct > 2:
        return 20.0
    return 0.0


def _score_bm_ratio(bm: float) -> float:
    if bm > 1.0:
        return 100.0
    if bm >= 0.6:
        return 80.0
    if bm >= 0.4:
        return 60.0
    if bm >= 0.2:
        return 40.0
    if bm >= 0.06:
        return 20.0
    return 0.0


def _score_roa_pct(roa: float) -> float:
    if roa > 15:
        return 100.0
    if roa > 10:
        return 80.0
    if roa > 5:
        return 60.0
    if roa > 2:
        return 40.0
    if roa > 0:
        return 20.0
    return 0.0


def _asset_growth_score(ag_pct: float) -> float:
    if ag_pct > 30:
        return 100.0
    if ag_pct > 15:
        return 80.0
    if ag_pct > 5:
        return 60.0
    if ag_pct > 0:
        return 40.0
    return 0.0


def _inv_penalty(inv_excess: float) -> float:
    if inv_excess <= 0:
        return 0.0
    if inv_excess <= 10:
        return 20.0
    if inv_excess <= 25:
        return 40.0
    return 60.0


def _size_score(val: float) -> float:
    """val = TEV or market cap in USD."""
    if val < 100_000_000:
        return 100.0
    if val < 250_000_000:
        return 85.0
    if val < 500_000_000:
        return 70.0
    if val < 1_000_000_000:
        return 50.0
    if val < 2_000_000_000:
        return 30.0
    return 10.0


def _entry_range_score(pct_in_range: float) -> float:
    if pct_in_range <= 10:
        return 100.0
    if pct_in_range <= 25:
        return 80.0
    if pct_in_range <= 40:
        return 60.0
    if pct_in_range <= 60:
        return 40.0
    if pct_in_range <= 80:
        return 20.0
    return 0.0


def _tier(composite: float) -> str:
    if composite >= 75:
        return "strong"
    if composite >= 55:
        return "watch"
    if composite >= 35:
        return "borderline"
    return "fail"


def _cap100(x: float) -> float:
    return min(100.0, max(0.0, x))


@dataclass
class YartsevaResult:
    ticker: str
    stage1_passed: bool
    stage1_failures: list[str] = field(default_factory=list)
    composite: float | None = None
    tier: str | None = None
    short_sell_flag: bool = False
    fcf_yield_score: float | None = None
    value_score: float | None = None
    profitability_score: float | None = None
    investment_quality_score: float | None = None
    size_score: float | None = None
    entry_timing_score: float | None = None
    fcf_yield_pct: float | None = None
    book_to_market: float | None = None
    roa_pct: float | None = None
    asset_growth_pct: float | None = None
    ebitda_growth_pct: float | None = None
    inv_excess_pp: float | None = None
    entry_range_pct: float | None = None
    error: str | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def score_yartseva(snap: YartsevaSnapshot) -> YartsevaResult:
    """Apply Stage 1 + Stage 2. If Stage 1 fails, composite is None (or we could still compute for display)."""
    r = YartsevaResult(ticker=snap.ticker, stage1_passed=False)
    r.snapshot = {k: v for k, v in asdict(snap).items() if k != "error"}

    if snap.error:
        r.error = snap.error
        r.stage1_failures.append("fetch_error")
        return r

    failures: list[str] = []
    mc = snap.market_cap
    if mc is None:
        failures.append("missing_market_cap")
    elif mc <= MCAP_MIN:
        failures.append("market_cap_below_floor")
    elif mc >= MCAP_MAX:
        failures.append("market_cap_above_ceiling")

    sec = (snap.sector or "").strip()
    if sec in EXCLUDED_SECTORS:
        failures.append("sector_excluded")

    if snap.ebitda_ttm is None or snap.ebitda_ttm <= 0:
        failures.append("ebitda_not_positive")

    om = snap.operating_margin_ttm
    if om is None or om <= 0:
        failures.append("operating_margin_not_positive")

    if snap.free_cash_flow_ttm is None or snap.free_cash_flow_ttm <= 0:
        failures.append("fcf_not_positive")

    teq = snap.total_equity_mrq
    if teq is None or teq <= 0:
        failures.append("book_value_not_positive")

    yoy = snap.yoy_total_assets_growth
    if yoy is None or yoy <= 0:
        failures.append("assets_not_growing_yoy")

    r.stage1_failures = failures
    r.stage1_passed = len(failures) == 0

    # Short-sell flag (independent of Stage 1 pass)
    mc200 = mc is not None and mc < 200_000_000
    r.short_sell_flag = bool(
        teq is not None
        and teq <= 0
        and om is not None
        and om < 0
        and mc200
        and yoy is not None
        and yoy < 0
    )

    if not r.stage1_passed:
        return r

    assert mc is not None and mc > 0

    # --- Scoring ---
    fcf_ttm = snap.free_cash_flow_ttm or 0.0
    fcf_yield_pct = (fcf_ttm / mc) * 100
    r.fcf_yield_pct = fcf_yield_pct
    r.fcf_yield_score = _score_fcf_yield_pct(fcf_yield_pct)

    bm = (teq or 0) / mc
    r.book_to_market = bm
    v_base = _score_bm_ratio(bm)
    v = v_base
    if snap.ps_ratio is not None and snap.ps_ratio < 0.6:
        v += 5
    if snap.forward_pe is not None and snap.forward_pe < 12:
        v += 3
    if snap.peg_ratio is not None and snap.peg_ratio < 1.0:
        v += 2
    r.value_score = _cap100(v)

    ta = snap.total_assets_mrq
    ni = snap.net_income_ttm
    roa_pct = (ni / ta * 100) if (ta and ta > 0 and ni is not None) else None
    r.roa_pct = roa_pct
    prof = _score_roa_pct(roa_pct) if roa_pct is not None else 0.0
    rev_ttm = snap.revenue_ttm or 0.0
    ebitda_ttm = snap.ebitda_ttm or 0.0
    ebitda_margin = (ebitda_ttm / rev_ttm) if rev_ttm > 0 else 0.0
    if ebitda_margin > 0.20:
        prof += 10
    elif ebitda_margin > 0.10:
        prof += 5
    r.profitability_score = _cap100(prof)

    ag_pct = (yoy or 0) * 100
    r.asset_growth_pct = ag_pct
    iq_base = _asset_growth_score(ag_pct)

    e_prev = snap.ebitda_prior_ttm
    e_cur = snap.ebitda_ttm
    eg_pct = None
    if e_cur is not None and e_prev is not None and abs(e_prev) > 1e-6:
        eg_pct = (e_cur - e_prev) / abs(e_prev) * 100
    elif snap.ebitda_growth_pct_annual is not None:
        # The path that is actually taken. See _annual_yoy: the quarterly one
        # needs eight quarters and yfinance returns four to seven.
        eg_pct = snap.ebitda_growth_pct_annual
    r.ebitda_growth_pct = eg_pct
    inv_excess = None
    if eg_pct is not None:
        inv_excess = ag_pct - eg_pct
        r.inv_excess_pp = inv_excess
    penalty = _inv_penalty(inv_excess if inv_excess is not None else 0.0)
    r.investment_quality_score = max(0.0, iq_base - penalty)

    size_basis = (
        snap.enterprise_value if snap.enterprise_value and snap.enterprise_value > 0 else mc
    )
    r.size_score = _size_score(size_basis)

    pc = snap.price_current
    hi = snap.price_52w_high
    lo = snap.price_52w_low
    er = None
    if pc and hi and lo and hi > lo:
        er = (pc - lo) / (hi - lo) * 100
    r.entry_range_pct = er
    ent = _entry_range_score(er) if er is not None else 0.0
    r6 = snap.return_6m_pct
    if r6 is not None:
        if r6 < -20:
            ent += 10
        elif -20 <= r6 <= -10:
            ent += 5
    r.entry_timing_score = _cap100(ent)

    comp = (
        (r.fcf_yield_score or 0) * 0.30
        + (r.value_score or 0) * 0.25
        + (r.profitability_score or 0) * 0.15
        + (r.investment_quality_score or 0) * 0.15
        + (r.size_score or 0) * 0.10
        + (r.entry_timing_score or 0) * 0.05
    )
    r.composite = round(comp, 2)
    r.tier = _tier(comp)

    return r


def run_yartseva_for_ticker(ticker: str) -> dict[str, Any]:
    snap = fetch_yartseva_snapshot(ticker)
    result = score_yartseva(snap)
    return result.to_dict()
