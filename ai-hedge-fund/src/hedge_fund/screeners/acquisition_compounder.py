"""
Acquisition / bolt-on compounder screener — quantitative filters + 9-factor score (/45).

Data via yfinance (annual + quarterly TTM). Many qualitative items (M&A style, management)
are not automatable; organic growth uses revenue YoY as a proxy. Verify in filings.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd
import yfinance as yf

from hedge_fund.screeners.yartseva import _f, _sum_q

logger = logging.getLogger(__name__)

# --- Step 1 thresholds ---
MIN_REV_CAGR_5Y = 0.10
MIN_EPS_OR_FCFPS_CAGR_5Y = 0.10
MIN_REV_YOY_PROXY = 0.03  # "organic" proxy
MIN_ROIC = 0.12
MIN_FCF_CONVERSION = 0.80
MAX_NET_DEBT_TO_EBITDA = 3.0
MIN_INTEREST_COVERAGE = 4.0
MAX_SHARE_CAGR_5Y = 0.02

# Step 2 optional (quality)
T2_MIN_REV_CAGR = 0.12
T2_MIN_FCF_MARGIN = 0.10
T2_MIN_ROIC = 0.15
T2_MAX_LEVERAGE = 2.5

# Red flags
RF_MAX_REV_YOY = 0.0
RF_MIN_FCF_CONV = 0.60
RF_MAX_LEVERAGE = 4.0
RF_MAX_DILUTION_CAGR = 0.05

AVOID_INDUSTRY_PATTERNS = re.compile(
    r"oil|gas|coal|copper|gold|silver|mining|steel|uranium|commodit|integrated\s+oil|"
    r"exploration|drilling|shipping\s+line|ocean\s+freight",
    re.I,
)
PREFER_INDUSTRY_PATTERNS = re.compile(
    r"software|saas|application|health\s*care|medical|industrial|distribution|"
    r"professional\s+services|consult|testing|inspection|certification|machinery|"
    r"facility|compliance|business\s+services",
    re.I,
)


def _sorted_annual_values(df: pd.DataFrame | None, row: str) -> list[float]:
    """Oldest → newest annual values for a line item."""
    if df is None or df.empty or row not in df.index:
        return []
    s = df.loc[row]
    pairs: list[tuple[pd.Timestamp, float]] = []
    for c in s.index:
        try:
            ts = pd.Timestamp(c)
        except Exception:
            continue
        v = s[c]
        if pd.notna(v):
            pairs.append((ts, float(v)))
    pairs.sort(key=lambda x: x[0])
    return [p[1] for p in pairs]


def _find_income_row(inc: pd.DataFrame | None, *candidates: str) -> str | None:
    if inc is None or inc.empty:
        return None
    for c in candidates:
        if c in inc.index:
            return c
    return None


def _cagr_5y(values: list[float]) -> float | None:
    if len(values) < 6:
        return None
    old, new = values[-6], values[-1]
    if old <= 0 or new <= 0:
        return None
    return (new / old) ** (1 / 5) - 1


def _geom_annual_growth_over_span(values: list[float]) -> float | None:
    """CAGR over available annual points (oldest→newest); use when fewer than 6 FY columns."""
    if len(values) < 2:
        return None
    old, new = values[0], values[-1]
    n = len(values) - 1
    if old <= 0 or new <= 0 or n < 1:
        return None
    return (new / old) ** (1 / n) - 1


def _yoy_latest(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    a, b = values[-2], values[-1]
    if a <= 0:
        return None
    return (b - a) / a


def _margin_series(inc: pd.DataFrame | None, rev_row: str, num_row: str) -> list[float]:
    if inc is None:
        return []
    if rev_row not in inc.index or num_row not in inc.index:
        return []
    revs = _sorted_annual_values(inc, rev_row)
    nums = _sorted_annual_values(inc, num_row)
    n = min(len(revs), len(nums), 6)
    if n < 2:
        return []
    revs, nums = revs[-n:], nums[-n:]
    out: list[float] = []
    for rv, nv in zip(revs, nums, strict=False):
        if rv and rv > 0:
            out.append(nv / rv)
    return out


def _margin_trend_stable_or_up(margins: list[float]) -> bool:
    if len(margins) < 2:
        return False
    # last vs first with 1pp tolerance for noise
    return margins[-1] >= margins[0] - 0.01


def _impairment_last_5y(inc: pd.DataFrame | None) -> float:
    if inc is None or inc.empty:
        return 0.0
    total = 0.0
    for idx in inc.index:
        if "impairment" in str(idx).lower() and "goodwill" in str(idx).lower():
            s = inc.loc[idx]
            for v in s.tail(5):
                if pd.notna(v) and float(v) < 0:
                    total += abs(float(v))
    return total


def _latest_q_bs(q_bs: pd.DataFrame | None, names: tuple[str, ...]) -> float | None:
    if q_bs is None or q_bs.empty:
        return None
    for n in names:
        if n in q_bs.index:
            return _f(q_bs.loc[n].iloc[0])
    return None


def _quarterly_sorted_values(q_df: pd.DataFrame | None, row: str) -> list[float]:
    if q_df is None or row not in q_df.index:
        return []
    s = q_df.loc[row]
    pairs: list[tuple[pd.Timestamp, float]] = []
    for c in s.index:
        try:
            ts = pd.Timestamp(c)
        except Exception:
            continue
        v = s[c]
        if pd.notna(v):
            pairs.append((ts, float(v)))
    pairs.sort(key=lambda x: x[0])
    return [p[1] for p in pairs]


def _rolling_ttm_sum_from_quarters(vals: list[float]) -> list[float]:
    """Oldest→newest TTM (rolling sum of 4 consecutive quarters)."""
    if len(vals) < 4:
        return []
    out: list[float] = []
    for i in range(len(vals) - 3):
        out.append(sum(vals[i : i + 4]))
    return out


def _cagr_ttm_5y(ttm: list[float]) -> float | None:
    """5-year CAGR from TTM series (compare TTM ~5y apart ≈ 20 quarters)."""
    if len(ttm) < 21:
        return None
    old, new = ttm[-21], ttm[-1]
    if old <= 0 or new <= 0:
        return None
    return (new / old) ** (1 / 5) - 1


def _ttm_yoy(ttm: list[float]) -> float | None:
    """TTM vs same metric one year earlier (4 TTM steps back)."""
    if len(ttm) < 5:
        return None
    old, new = ttm[-5], ttm[-1]
    if old <= 0:
        return None
    return (new - old) / old


def _fcps_ttm_series(q_cf: pd.DataFrame | None, q_inc: pd.DataFrame | None) -> list[float]:
    """FCF per share (TTM FCF / average diluted shares over those 4 quarters)."""
    if q_cf is None or q_inc is None:
        return []
    fcf = _quarterly_sorted_values(q_cf, "Free Cash Flow")
    sh_row = _find_income_row(q_inc, "Diluted Average Shares", "Basic Average Shares")
    if not sh_row:
        return []
    sh = _quarterly_sorted_values(q_inc, sh_row)
    n = min(len(fcf), len(sh))
    if n < 4:
        return []
    fcf, sh = fcf[-n:], sh[-n:]
    out: list[float] = []
    for i in range(len(fcf) - 3):
        ttm_f = sum(fcf[i : i + 4])
        ttm_sh = sum(sh[i : i + 4]) / 4.0
        if ttm_sh > 0:
            out.append(ttm_f / ttm_sh)
    return out


def _compute_roic_fallback(
    ebit_ttm: float | None,
    tax_rate: float | None,
    total_debt: float | None,
    cash: float | None,
    equity: float | None,
) -> float | None:
    """NOPAT / (debt + equity - cash), rough."""
    if ebit_ttm is None or ebit_ttm <= 0:
        return None
    tr = 0.25 if tax_rate is None else float(tax_rate)
    if tr > 1:
        tr = tr / 100.0
    tr = max(0.0, min(0.35, tr))
    nopat = ebit_ttm * (1 - tr)
    if total_debt is None or equity is None:
        return None
    c = cash or 0.0
    ic = total_debt + equity - c
    if ic <= 0:
        return None
    return nopat / ic


@dataclass
class AcquisitionSnapshot:
    ticker: str
    sector: str | None = None
    industry: str | None = None
    revenue_cagr_5y: float | None = None
    eps_cagr_5y: float | None = None
    fcf_ps_cagr_5y: float | None = None
    revenue_yoy: float | None = None
    roic: float | None = None
    fcf_conversion: float | None = None
    gross_margin_trend_ok: bool | None = None
    operating_margin_trend_ok: bool | None = None
    net_debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    share_cagr_5y: float | None = None
    impairment_5y_sum: float | None = None
    revenue_ttm: float | None = None
    net_income_ttm: float | None = None
    fcf_ttm: float | None = None
    ebitda_ttm: float | None = None
    error: str | None = None


def fetch_acquisition_snapshot(ticker: str) -> AcquisitionSnapshot:
    t = yf.Ticker(ticker.strip().upper())
    snap = AcquisitionSnapshot(ticker=ticker.strip().upper())
    try:
        info = t.info or {}
        if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
            snap.error = "no_quote_or_info"
            return snap

        snap.sector = info.get("sector") or None
        snap.industry = info.get("industry") or None

        roic_raw = info.get("returnOnInvestedCapital") or info.get("returnOnCapitalEmployed")
        if roic_raw is not None:
            r = float(roic_raw)
            snap.roic = r if abs(r) <= 1.0 else r / 100.0

        inc_a = t.income_stmt
        cf_a = t.cashflow
        q_inc = t.quarterly_income_stmt
        q_cf = t.quarterly_cashflow
        q_bs = t.quarterly_balance_sheet

        rev_row_a = _find_income_row(inc_a, "Total Revenue", "Revenue", "Operating Revenue")
        rev_q = _find_income_row(q_inc, "Total Revenue", "Revenue", "Operating Revenue")

        # Revenue CAGR / YoY: prefer 6+ annual points; else quarterly TTM series (~21 TTM points)
        if rev_row_a:
            revs_a = _sorted_annual_values(inc_a, rev_row_a)
            if len(revs_a) >= 6:
                snap.revenue_cagr_5y = _cagr_5y(revs_a)
                snap.revenue_yoy = _yoy_latest(revs_a)
            elif len(revs_a) >= 2:
                snap.revenue_cagr_5y = _geom_annual_growth_over_span(revs_a)
                snap.revenue_yoy = _yoy_latest(revs_a)
        if snap.revenue_cagr_5y is None and rev_q and q_inc is not None:
            rq = _quarterly_sorted_values(q_inc, rev_q)
            rev_ttm = _rolling_ttm_sum_from_quarters(rq)
            c5 = _cagr_ttm_5y(rev_ttm)
            if c5 is not None:
                snap.revenue_cagr_5y = c5
            y = _ttm_yoy(rev_ttm)
            if y is not None:
                snap.revenue_yoy = y
        if snap.revenue_yoy is None:
            rg = info.get("revenueGrowth")
            if rg is not None:
                try:
                    g = float(rg)
                    snap.revenue_yoy = g if abs(g) <= 1 else g / 100.0
                except (TypeError, ValueError):
                    pass

        eps_row_a = _find_income_row(inc_a, "Diluted EPS", "Basic EPS")
        if eps_row_a:
            eps_a = _sorted_annual_values(inc_a, eps_row_a)
            if len(eps_a) >= 6:
                snap.eps_cagr_5y = _cagr_5y(eps_a)
            elif len(eps_a) >= 2:
                snap.eps_cagr_5y = _geom_annual_growth_over_span(eps_a)
        if snap.eps_cagr_5y is None and q_inc is not None:
            eps_q = _find_income_row(q_inc, "Diluted EPS", "Basic EPS")
            if eps_q:
                eq = _quarterly_sorted_values(q_inc, eps_q)
                eps_ttm = _rolling_ttm_sum_from_quarters(eq)
                c5e = _cagr_ttm_5y(eps_ttm)
                if c5e is not None:
                    snap.eps_cagr_5y = c5e

        if cf_a is not None and inc_a is not None:
            fcf_row = "Free Cash Flow"
            if fcf_row in cf_a.index:
                fcf_a = _sorted_annual_values(cf_a, fcf_row)
                sh_r = _find_income_row(inc_a, "Diluted Average Shares", "Basic Average Shares")
                if sh_r and len(fcf_a) >= 2:
                    sh_vals = _sorted_annual_values(inc_a, sh_r)
                    n = min(len(fcf_a), len(sh_vals))
                    if n >= 2:
                        fv, sv = fcf_a[-n:], sh_vals[-n:]
                        fcps = [f / s for f, s in zip(fv, sv, strict=False) if s and s > 0]
                        if len(fcps) >= 6:
                            snap.fcf_ps_cagr_5y = _cagr_5y(fcps)
                        elif len(fcps) >= 2:
                            snap.fcf_ps_cagr_5y = _geom_annual_growth_over_span(fcps)
        if snap.fcf_ps_cagr_5y is None and q_cf is not None and q_inc is not None:
            fcps_ttm = _fcps_ttm_series(q_cf, q_inc)
            c5f = _cagr_ttm_5y(fcps_ttm)
            if c5f is not None:
                snap.fcf_ps_cagr_5y = c5f

        gp_row_a = _find_income_row(inc_a, "Gross Profit")
        if rev_row_a and gp_row_a and inc_a is not None:
            gm = _margin_series(inc_a, rev_row_a, gp_row_a)
            if gm:
                snap.gross_margin_trend_ok = _margin_trend_stable_or_up(gm)
        if snap.gross_margin_trend_ok is None and rev_q and q_inc is not None:
            gp_q = _find_income_row(q_inc, "Gross Profit")
            if gp_q:
                rt = _rolling_ttm_sum_from_quarters(_quarterly_sorted_values(q_inc, rev_q))
                gt = _rolling_ttm_sum_from_quarters(_quarterly_sorted_values(q_inc, gp_q))
                m = min(len(rt), len(gt))
                if m >= 2:
                    rt, gt = rt[-m:], gt[-m:]
                    margins = [gt[i] / rt[i] for i in range(len(rt)) if rt[i] > 0]
                    snap.gross_margin_trend_ok = _margin_trend_stable_or_up(margins)

        oi_row_a = _find_income_row(inc_a, "Operating Income", "Operating Income Loss")
        if rev_row_a and oi_row_a and inc_a is not None:
            om = _margin_series(inc_a, rev_row_a, oi_row_a)
            if om:
                snap.operating_margin_trend_ok = _margin_trend_stable_or_up(om)
        if snap.operating_margin_trend_ok is None and rev_q and q_inc is not None:
            oi_q = _find_income_row(q_inc, "Operating Income", "Operating Income Loss")
            if oi_q:
                rt = _rolling_ttm_sum_from_quarters(_quarterly_sorted_values(q_inc, rev_q))
                ot = _rolling_ttm_sum_from_quarters(_quarterly_sorted_values(q_inc, oi_q))
                m = min(len(rt), len(ot))
                if m >= 2:
                    rt, ot = rt[-m:], ot[-m:]
                    omarg = [ot[i] / rt[i] for i in range(len(rt)) if rt[i] > 0]
                    snap.operating_margin_trend_ok = _margin_trend_stable_or_up(omarg)

        ni_ttm = _sum_q(q_inc, "Net Income", 0, 4)
        fcf_ttm = _sum_q(q_cf, "Free Cash Flow", 0, 4) if q_cf is not None else None
        snap.net_income_ttm = ni_ttm
        snap.fcf_ttm = fcf_ttm
        rev_ttm = _sum_q(q_inc, "Total Revenue", 0, 4)
        snap.revenue_ttm = rev_ttm
        snap.ebitda_ttm = _sum_q(q_inc, "EBITDA", 0, 4)

        if fcf_ttm is not None and ni_ttm is not None and abs(ni_ttm) > 1e-6:
            snap.fcf_conversion = fcf_ttm / ni_ttm
        elif fcf_ttm is not None and ni_ttm is not None and abs(ni_ttm) <= 1e-6:
            snap.fcf_conversion = None

        total_debt = _latest_q_bs(q_bs, ("Total Debt", "Total Liabilities Net Minority Interest"))
        cash = _latest_q_bs(
            q_bs,
            (
                "Cash And Cash Equivalents",
                "Cash Cash Equivalents And Short Term Investments",
                "Cash Financial",
            ),
        )
        ebitda = snap.ebitda_ttm
        if total_debt is not None and cash is not None and ebitda is not None and ebitda > 0:
            net_debt = max(0.0, total_debt - cash)
            snap.net_debt_to_ebitda = net_debt / ebitda

        ebit_ttm = _sum_q(q_inc, "EBIT", 0, 4)
        if ebit_ttm is None and q_inc is not None and "Operating Income" in q_inc.index:
            ebit_ttm = _sum_q(q_inc, "Operating Income", 0, 4)
        int_ttm = _sum_q(q_inc, "Interest Expense", 0, 4)
        if int_ttm is not None:
            int_ttm = abs(int_ttm)
        if ebit_ttm is not None and int_ttm is not None and int_ttm > 1e-6:
            snap.interest_coverage = ebit_ttm / int_ttm
        elif int_ttm is not None and int_ttm <= 1e-6:
            snap.interest_coverage = 999.0

        if inc_a is not None:
            sh_r2 = _find_income_row(inc_a, "Diluted Average Shares", "Basic Average Shares")
            if sh_r2:
                shv = _sorted_annual_values(inc_a, sh_r2)
                if len(shv) >= 6:
                    snap.share_cagr_5y = _cagr_5y(shv)
                elif len(shv) >= 2:
                    snap.share_cagr_5y = _geom_annual_growth_over_span(shv)
        if snap.share_cagr_5y is None and q_inc is not None:
            sh_rq = _find_income_row(q_inc, "Diluted Average Shares", "Basic Average Shares")
            if sh_rq:
                shq = _quarterly_sorted_values(q_inc, sh_rq)
                if len(shq) >= 21:
                    o, n = shq[-21], shq[-1]
                    if o > 0 and n > 0:
                        snap.share_cagr_5y = (n / o) ** (1 / 5) - 1

        if inc_a is not None:
            snap.impairment_5y_sum = _impairment_last_5y(inc_a)
        elif q_inc is not None:
            snap.impairment_5y_sum = _impairment_last_5y(q_inc)

        if snap.roic is None:
            tr = _f(info.get("taxRate"))
            ce = _latest_q_bs(
                q_bs,
                ("Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"),
            )
            snap.roic = _compute_roic_fallback(ebit_ttm, tr, total_debt, cash, ce)

    except Exception as e:
        logger.warning("acquisition fetch failed for %s: %s", ticker, e)
        snap.error = str(e)
    return snap


def _score_1_5(x: float | None, lo: float, hi: float) -> int:
    """Map metric to 1–5 (higher x = better); None → 1."""
    if x is None:
        return 1
    if x >= hi:
        return 5
    if x >= lo + (hi - lo) * 0.75:
        return 4
    if x >= lo + (hi - lo) * 0.5:
        return 3
    if x >= lo + (hi - lo) * 0.25:
        return 2
    return 1


def _score_leverage_nd_ebitda(nd: float | None) -> int:
    """Lower net debt/EBITDA is better."""
    if nd is None:
        return 1
    if nd < 1.0:
        return 5
    if nd < 1.5:
        return 4
    if nd < 2.5:
        return 3
    if nd < 3.5:
        return 2
    return 1


def _score_share_dilution(cagr: float | None) -> int:
    """Lower share-count CAGR is better."""
    if cagr is None:
        return 1
    if cagr <= 0:
        return 5
    if cagr < 0.01:
        return 4
    if cagr < 0.02:
        return 3
    if cagr < 0.05:
        return 2
    return 1


@dataclass
class AcquisitionResult:
    ticker: str
    stage1_passed: bool
    stage1_failures: list[str] = field(default_factory=list)
    tier2_passed: bool = False
    red_flags: list[str] = field(default_factory=list)
    industry_avoid: bool = False
    industry_prefer_match: bool = False
    total_score: float | None = None
    tier: str | None = None
    scores: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_acquisition_compounder(snap: AcquisitionSnapshot) -> AcquisitionResult:
    r = AcquisitionResult(ticker=snap.ticker, stage1_passed=False)
    r.snapshot = {k: v for k, v in asdict(snap).items() if k != "error"}

    if snap.error:
        r.error = snap.error
        r.stage1_failures.append("fetch_error")
        return r

    text = f"{snap.sector or ''} {snap.industry or ''}"
    r.industry_avoid = bool(AVOID_INDUSTRY_PATTERNS.search(text))
    r.industry_prefer_match = bool(PREFER_INDUSTRY_PATTERNS.search(text))

    failures: list[str] = []

    if snap.revenue_cagr_5y is None:
        failures.append("revenue_cagr_missing_or_short_history")
    elif snap.revenue_cagr_5y <= MIN_REV_CAGR_5Y:
        failures.append("revenue_cagr_5y")

    eps_ok = snap.eps_cagr_5y is not None and snap.eps_cagr_5y > MIN_EPS_OR_FCFPS_CAGR_5Y
    fcfps_ok = snap.fcf_ps_cagr_5y is not None and snap.fcf_ps_cagr_5y > MIN_EPS_OR_FCFPS_CAGR_5Y
    if not eps_ok and not fcfps_ok:
        if snap.eps_cagr_5y is None and snap.fcf_ps_cagr_5y is None:
            failures.append("eps_and_fcfps_cagr_missing")
        else:
            failures.append("eps_or_fcfps_cagr")

    if snap.revenue_yoy is None:
        failures.append("revenue_yoy_missing")
    elif snap.revenue_yoy <= MIN_REV_YOY_PROXY:
        failures.append("revenue_yoy_proxy_organic")

    if snap.roic is None:
        failures.append("roic_missing")
    elif snap.roic <= MIN_ROIC:
        failures.append("roic")

    if snap.fcf_conversion is None:
        failures.append("fcf_conversion_missing")
    elif snap.fcf_conversion <= MIN_FCF_CONVERSION:
        failures.append("fcf_conversion")

    if snap.gross_margin_trend_ok is not True:
        failures.append("gross_margin_trend")

    if snap.operating_margin_trend_ok is not True:
        failures.append("operating_margin_trend")

    if snap.net_debt_to_ebitda is None:
        failures.append("leverage_missing")
    elif snap.net_debt_to_ebitda >= MAX_NET_DEBT_TO_EBITDA:
        failures.append("net_debt_ebitda")

    if snap.interest_coverage is None:
        failures.append("interest_coverage_missing")
    elif snap.interest_coverage < MIN_INTEREST_COVERAGE:
        failures.append("interest_coverage")

    if snap.share_cagr_5y is None:
        failures.append("share_count_cagr_missing")
    elif snap.share_cagr_5y >= MAX_SHARE_CAGR_5Y:
        failures.append("share_dilution")

    # Goodwill impairments: flag large charges vs revenue (heuristic)
    rev_ttm = snap.revenue_ttm or 0.0
    if snap.impairment_5y_sum and rev_ttm > 0 and snap.impairment_5y_sum > 0.05 * rev_ttm:
        failures.append("goodwill_impairment_material")

    if r.industry_avoid:
        failures.append("industry_avoid_list")

    r.stage1_failures = failures
    r.stage1_passed = len(failures) == 0

    # Red flags (report even if stage 1 fails)
    rf: list[str] = []
    if snap.revenue_yoy is not None and snap.revenue_yoy <= RF_MAX_REV_YOY:
        rf.append("organic_proxy_lte_0")
    if snap.fcf_conversion is not None and snap.fcf_conversion < RF_MIN_FCF_CONV:
        rf.append("fcf_conversion_lt_60pct")
    if snap.net_debt_to_ebitda is not None and snap.net_debt_to_ebitda > RF_MAX_LEVERAGE:
        rf.append("leverage_gt_4x")
    if snap.share_cagr_5y is not None and snap.share_cagr_5y > RF_MAX_DILUTION_CAGR:
        rf.append("dilution_gt_5pct_cagr")
    r.red_flags = rf

    # Tier 2 optional
    r.tier2_passed = bool(
        r.stage1_passed
        and snap.revenue_cagr_5y is not None
        and snap.revenue_cagr_5y > T2_MIN_REV_CAGR
        and snap.roic is not None
        and snap.roic > T2_MIN_ROIC
        and snap.net_debt_to_ebitda is not None
        and snap.net_debt_to_ebitda < T2_MAX_LEVERAGE
        and snap.revenue_ttm
        and snap.fcf_ttm is not None
        and (snap.fcf_ttm / snap.revenue_ttm) > T2_MIN_FCF_MARGIN
        and snap.fcf_ps_cagr_5y is not None
        and snap.revenue_cagr_5y is not None
        and snap.fcf_ps_cagr_5y > snap.revenue_cagr_5y
    )

    # 9-factor score 1–5 each (45 max) — uses available data; management/industry fragmentation are proxies
    s_org = _score_1_5(snap.revenue_yoy, 0.0, 0.20)
    s_roic = _score_1_5(snap.roic, 0.08, 0.25)
    s_fcf = _score_1_5(snap.fcf_conversion, 0.5, 1.2)
    s_bs = _score_leverage_nd_ebitda(snap.net_debt_to_ebitda)
    s_acq = 3  # discipline — not observable in price data
    if snap.operating_margin_trend_ok is True:
        s_mar = 4
    else:
        s_mar = 2
    s_dil = _score_share_dilution(snap.share_cagr_5y)
    s_frag = 3 if r.industry_prefer_match else 2
    s_mgmt = 4 if not rf else 2

    r.scores = {
        "organic_growth": s_org,
        "roic": s_roic,
        "fcf_conversion": s_fcf,
        "balance_sheet": s_bs,
        "acquisition_discipline": s_acq,
        "margin_stability": s_mar,
        "share_dilution": s_dil,
        "industry_fit": s_frag,
        "management_quality_proxy": s_mgmt,
    }
    total = float(sum(r.scores.values()))
    r.total_score = round(total, 2)

    if total >= 40:
        r.tier = "elite"
    elif total >= 35:
        r.tier = "strong"
    elif total >= 28:
        r.tier = "watch"
    else:
        r.tier = "weak"

    return r


def run_acquisition_compounder_for_ticker(ticker: str) -> dict[str, Any]:
    snap = fetch_acquisition_snapshot(ticker)
    result = score_acquisition_compounder(snap)
    return result.to_dict()
