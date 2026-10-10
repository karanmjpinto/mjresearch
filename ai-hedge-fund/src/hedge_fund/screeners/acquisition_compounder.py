"""
Acquisition / bolt-on compounder screener — quantitative filters + 10-factor score (/50).

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

from hedge_fund.screeners import principles
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

#: The size band this screen is for, in the currency the company is *quoted*
#: in — not the one it reports accounts in. See `snap.currency` for why those
#: differ and what reading the wrong one cost.
#:
#: There was no cap filter here at all, which is the single reason this read
#: as a large-cap screen: only its default universe made it one. Every test
#: below — ROIC above 12%, FCF conversion above 80%, a share count that does
#: not grow — is a quality test that applies at any size, and the desk this
#: serves is looking for quality small and mid caps. So the band is explicit
#: and the universe is free to change.
#:
#: Roughly $500m to $20bn at either end. The thresholds are round numbers
#: rather than converted ones, because this is a band boundary and not a
#: valuation: a tenth of a percent of FX error cannot move a company between
#: "mid cap" and "mega cap", and a pretend-precise rate would imply it could.
#:
#: The floor is held at $500m by choice. Below it the coverage gap is wider
#: still — the genuinely unexamined shelf is $50m to $500m — but so are the
#: spread, the disclosure gaps and the research cost per name, and a desk run
#: by one person has to be able to act on what it finds. Recorded as the
#: `small-and-mid-only` principle.
#:
#: Unlisted currencies are refused rather than converted, following
#: `MIN_MARKET_CAP_BY_CURRENCY` in the Kiyohara screen. The failure mode that
#: rule exists to stop is a yen cap read against a dollar band, where every
#: Japanese company looks like a mega cap and the screen returns nothing while
#: looking like it ran.
#:
#: The Nordic and Swiss entries are here because the data layer has carried
#: `nordic.py` (.ST, .CO, .HE) since long before this screen had a band, so a
#: Stockholm ticker was always reachable by searching for it. Without a krona
#: band every Swedish company failed `cap_band_unknown_currency` — refused on
#: a size filter nobody had actually set for it. Found by running a real
#: Stockholm small cap through the screen rather than by any test, because
#: `test_every_universe_currency_has_a_band` only knows about the eight
#: shipped universes and Sweden is not one of them.
CAP_BAND_BY_CURRENCY: dict[str, tuple[float, float]] = {
    "USD": (500_000_000, 20_000_000_000),
    "CAD": (700_000_000, 28_000_000_000),
    "AUD": (750_000_000, 30_000_000_000),
    "GBP": (400_000_000, 16_000_000_000),
    "EUR": (450_000_000, 18_000_000_000),
    "JPY": (75_000_000_000, 3_000_000_000_000),
    "HKD": (4_000_000_000, 155_000_000_000),
    "SEK": (5_000_000_000, 200_000_000_000),
    "DKK": (3_500_000_000, 140_000_000_000),
    "NOK": (5_000_000_000, 200_000_000_000),
    "CHF": (400_000_000, 16_000_000_000),
}

#: --- The reinvestment leg ---
#:
#: Chuck Akre's three-legged stool is an extraordinary business, management who
#: allocate well, and a *reinvestment runway*. This screen measured the first
#: two and not the third, which is the difference between a good business and a
#: compounder: `MIN_ROIC` says the company earns well on the capital it already
#: has, and says nothing about whether there is anywhere to put the next dollar
#: at that rate. A high-return business with nowhere to reinvest is a dividend,
#: not a compounding machine.
#:
#: Two measurements, multiplied, because neither alone is the thing:
#:
#:   reinvestment rate   how much of the cash generated goes back in
#:   ROIIC               what the *newly deployed* capital earns, not the
#:                       average over capital sunk years ago
#:
#: Their product is the growth the business can fund from its own operations —
#: the fundamental growth equation, g = reinvestment × return. A company
#: reinvesting 80% at 25% implies 20% compounding; one reinvesting 20% at 10%
#: implies 2%, however good its headline ROIC looks.
#:
#: ROIIC needs the capital base to have actually moved to mean anything: a
#: company whose invested capital is flat produces a denominator near zero and
#: an arbitrarily large ratio. So it is only computed when invested capital
#: grew by at least this fraction, and is None otherwise — scored neutral
#: rather than guessed. Note that a *shrinking* capital base with rising
#: profit is often an excellent capital-light business; it is simply not a
#: thing this ratio can describe, and pretending otherwise would punish it.
MIN_IC_GROWTH_FOR_ROIIC = 0.05

#: The implied compounding rate, scored 1-5 between these. 3% is a business
#: funding little more than inflation; 18% is a genuine compounder.
REINVEST_SCORE_LO = 0.03
REINVEST_SCORE_HI = 0.18

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
            # A non-date column in a statement frame; skipping it is intended.
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
    nopat = ebit_ttm * (1 - _effective_tax_rate(tax_rate))
    if total_debt is None or equity is None:
        return None
    c = cash or 0.0
    ic = total_debt + equity - c
    if ic <= 0:
        return None
    return nopat / ic


def _effective_tax_rate(tax_rate: float | None) -> float:
    """The tax rate NOPAT is computed at, clamped to something plausible.

    Extracted from `_compute_roic_fallback`, which did this inline, so ROIC
    and ROIIC are computed on the same basis. Two measures of return on
    capital that disagreed about tax would not be comparable, and the whole
    point of the pair is to compare them.
    """
    tr = 0.25 if tax_rate is None else float(tax_rate)
    if tr > 1:
        tr = tr / 100.0
    return max(0.0, min(0.35, tr))


def _invested_capital_series(bs_a: pd.DataFrame | None) -> list[float]:
    """Debt + equity - cash per annual balance sheet, oldest → newest.

    The same definition `_compute_roic_fallback` uses for its denominator, so
    the level and the increment are measured the same way.
    """
    if bs_a is None or bs_a.empty:
        return []

    def pick(*names: str) -> list[float]:
        for n in names:
            if n in bs_a.index:
                return _sorted_annual_values(bs_a, n)
        return []

    debt = pick("Total Debt", "Total Liabilities Net Minority Interest")
    equity = pick(
        "Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"
    )
    cash = pick(
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash Financial",
    )
    if not debt or not equity:
        return []

    n = min(len(debt), len(equity))
    # Cash is optional: a balance sheet without a cash line still gives a
    # usable, slightly conservative invested-capital figure.
    cash = cash[-n:] if len(cash) >= n else [0.0] * n
    debt, equity = debt[-n:], equity[-n:]
    return [debt[i] + equity[i] - cash[i] for i in range(n)]


def _roiic(
    ebit_series: list[float], ic_series: list[float], tax_rate: float | None
) -> float | None:
    """Return on *incremental* invested capital: ΔNOPAT / ΔIC over the span.

    None whenever the answer would be noise rather than a measurement: too
    few years, a capital base that barely moved (see
    `MIN_IC_GROWTH_FOR_ROIIC`), or one that shrank. Each of those is a real
    situation the ratio cannot describe, and a number produced anyway would be
    indistinguishable from one that means something.
    """
    n = min(len(ebit_series), len(ic_series))
    if n < 2:
        return None
    ebit, ic = ebit_series[-n:], ic_series[-n:]

    ic_old, ic_new = ic[0], ic[-1]
    if ic_old <= 0 or ic_new <= 0:
        return None
    d_ic = ic_new - ic_old
    if d_ic <= 0 or d_ic < MIN_IC_GROWTH_FOR_ROIIC * ic_old:
        return None

    tr = _effective_tax_rate(tax_rate)
    d_nopat = (ebit[-1] - ebit[0]) * (1 - tr)
    return d_nopat / d_ic


def _reinvestment_rate(cf_a: pd.DataFrame | None) -> float | None:
    """How much of operating cash flow goes back into the business.

    Capital expenditure plus acquisitions, over operating cash flow. Both
    outflows are reported negative, so they are taken as magnitudes.

    Acquisitions are included deliberately: this screen is about bolt-on
    compounders, and for a serial acquirer the acquisitions *are* the
    reinvestment. Counting only capex would score the whole strategy as
    reinvesting nothing.

    Capped at 1.0. A company spending more than it earns is reinvesting
    everything by this measure and the excess is funded by debt or issuance,
    which the leverage and dilution factors already judge — letting it run to
    3.0 here would turn an over-extended balance sheet into a high score.
    """
    if cf_a is None or cf_a.empty:
        return None

    def latest(*names: str) -> float | None:
        for n in names:
            if n in cf_a.index:
                vals = _sorted_annual_values(cf_a, n)
                if vals:
                    return vals[-1]
        return None

    ocf = latest("Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    if ocf is None or ocf <= 0:
        return None

    capex = latest("Capital Expenditure", "Purchase Of PPE") or 0.0
    acq = latest("Net Business Purchase And Sale", "Purchase Of Business") or 0.0
    spend = abs(capex) + abs(acq)
    if spend <= 0:
        return 0.0
    return min(1.0, spend / ocf)


@dataclass
class AcquisitionSnapshot:
    ticker: str
    sector: str | None = None
    industry: str | None = None
    #: The currency the cap is quoted in. Carried rather than assumed, because
    #: this screen now runs on eight universes across six currencies.
    currency: str | None = None
    market_cap: float | None = None
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
    #: The reinvestment leg. `implied_compounding` is the product of the two
    #: above it, and is the figure the score actually reads.
    reinvestment_rate: float | None = None
    roiic: float | None = None
    implied_compounding: float | None = None
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
        if not info or (
            info.get("regularMarketPrice") is None and info.get("currentPrice") is None
        ):
            snap.error = "no_quote_or_info"
            return snap

        snap.sector = info.get("sector") or None
        snap.industry = info.get("industry") or None
        # The *quote* currency, not the reporting currency, because that is
        # what `marketCap` is denominated in: it is shares times price, and
        # the price is whatever the exchange quotes.
        #
        # This read `financialCurrency` first and that was wrong. Evolution AB
        # trades in Stockholm and reports in euro — `currency` SEK,
        # `financialCurrency` EUR — so its 147.7bn SEK market cap was compared
        # against the euro band and rejected for exceeding the €18bn ceiling.
        # It is about €13bn and belongs inside the band. A false rejection,
        # and an invisible one, because "too big" is a plausible thing for
        # this screen to say about a company.
        #
        # Any issuer whose listing and accounts disagree hits this, which is
        # common across European and Asian cross-listings — precisely the
        # population a global small and mid-cap desk is looking at.
        snap.currency = (
            info.get("currency") or info.get("financialCurrency") or ""
        ).upper() or None
        snap.market_cap = _f(info.get("marketCap"))

        roic_raw = info.get("returnOnInvestedCapital") or info.get("returnOnCapitalEmployed")
        if roic_raw is not None:
            r = float(roic_raw)
            snap.roic = r if abs(r) <= 1.0 else r / 100.0

        inc_a = t.income_stmt
        cf_a = t.cashflow
        bs_a = t.balance_sheet
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
                (
                    "Stockholders Equity",
                    "Common Stock Equity",
                    "Total Equity Gross Minority Interest",
                ),
            )
            snap.roic = _compute_roic_fallback(ebit_ttm, tr, total_debt, cash, ce)

        # The reinvestment leg. Computed from annual statements rather than
        # the TTM figures above, because an increment needs two points in
        # time and a trailing window only gives one.
        snap.reinvestment_rate = _reinvestment_rate(cf_a)
        ebit_row_a = _find_income_row(inc_a, "EBIT", "Operating Income", "Operating Income Loss")
        if ebit_row_a and inc_a is not None:
            snap.roiic = _roiic(
                _sorted_annual_values(inc_a, ebit_row_a),
                _invested_capital_series(bs_a),
                _f(info.get("taxRate")),
            )
        if snap.reinvestment_rate is not None and snap.roiic is not None:
            snap.implied_compounding = snap.reinvestment_rate * snap.roiic

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


def cap_band(currency: str | None) -> tuple[float, float] | None:
    """The size band for a currency, or None when the currency is unlisted.

    None is a refusal, not a default. A missing band means the screen cannot
    say whether a company is the right size, and that has to surface as a
    named failure rather than as a silent pass.
    """
    if not currency:
        return None
    return CAP_BAND_BY_CURRENCY.get(currency.upper())


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

    # A standing exclusion, applied before anything is measured. These are
    # principles rather than screen rules — see screeners/principles.py — so
    # they are shared across every screen rather than restated in each, and
    # the failure names the principle that removed the company rather than
    # just saying it was excluded.
    _excl = principles.excluded_by(snap.sector, snap.industry)
    if _excl:
        failures.append(f"excluded_{_excl.replace('-', '_')}")

    # Size first, because it is the cheapest filter and the one that decides
    # whether this is the right shelf at all. A mega cap that passes every
    # quality test below is still not what this desk is looking for.
    band = cap_band(snap.currency)
    if snap.market_cap is None:
        failures.append("missing_market_cap")
    elif band is None:
        # Refused rather than guessed. See CAP_BAND_BY_CURRENCY.
        failures.append("cap_band_unknown_currency")
    elif snap.market_cap < band[0]:
        failures.append("market_cap_below_floor")
    elif snap.market_cap > band[1]:
        failures.append("market_cap_above_ceiling")

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

    # 10-factor score 1–5 each (50 max) — uses available data; management/industry fragmentation are proxies
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
    # Akre's third leg. Neutral rather than zero when it cannot be measured:
    # an unmeasurable runway is not a short one, and the guards in `_roiic`
    # decline to answer precisely in the cases where an answer would be noise.
    s_reinv = (
        3
        if snap.implied_compounding is None
        else _score_1_5(snap.implied_compounding, REINVEST_SCORE_LO, REINVEST_SCORE_HI)
    )

    r.scores = {
        "organic_growth": s_org,
        "roic": s_roic,
        "reinvestment_runway": s_reinv,
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

    # Rescaled from the nine-factor /45 in proportion, so a tier means what it
    # meant before: elite was 89% of the maximum and still is. Leaving the old
    # absolute cut-offs against a larger maximum would have quietly promoted
    # every company by roughly one tier.
    if total >= 44:
        r.tier = "elite"
    elif total >= 39:
        r.tier = "strong"
    elif total >= 31:
        r.tier = "watch"
    else:
        r.tier = "weak"

    return r


def run_acquisition_compounder_for_ticker(ticker: str) -> dict[str, Any]:
    snap = fetch_acquisition_snapshot(ticker)
    result = score_acquisition_compounder(snap)
    return result.to_dict()
