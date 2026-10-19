"""The AI supply-chain scarcity screen, after Cambrian's September 2026 thesis.

Cambrian Capital's argument, reduced to the parts that decide a list:

  1. As compute gets more valuable, the value accrues to the *scarce physical
     inputs* that make it — wafers, memory, capacitors, fab capacity — and
     many of those still trade at 1-5x revenue while software trades at 13-100x.
  2. Software is automated before factories are, so prefer companies that own
     plant and process know-how over fabless designers and software firms.
  3. In a fast-AI world, idle capacity, low utilisation and low margins are not
     defects but *torque*: fixed cost already paid, so incremental volume
     falls straight to profit. Which is why they read revenue multiples and not
     P/E — earnings are depressed exactly where the torque is largest.
  4. The customer base must be price-inelastic. That decides how far prices
     can rise and when they start rising.
  5. Supply cannot scale fast enough for the old gluts to return, so the
     cycle may not behave like the last ones.

WHAT IS COMPUTABLE HERE, AND WHAT IS NOT

Points 1-3 leave a financial trace and are scored:

  revenue multiple   market cap over next-twelve-month consensus revenue, their
                     own definition. Calendarised from the current and next
                     fiscal-year estimates, and converted when the listing
                     quotes in one currency and reports in another — see
                     `FX` below, because the provider's own ratio gets this
                     wrong by 8x for Hong Kong-listed foundries.
  owns factories     net plant over annual revenue. A fabless designer
                     reports almost none, so this is the filter that turns
                     "semiconductors" from an industry label into point 2.
                     Over revenue, not over assets: plant over assets failed
                     Yageo (goodwill) and Kyocera (a KDDI stake), both of
                     which own their lines.
  torque             degree of operating leverage: contribution over operating
                     profit, treating cash cost of goods as variable and
                     depreciation plus operating expense as fixed. Their own
                     illustration — 55 fixed, 30 variable, 15 profit — gives
                     4.7, which is the +47% profit on +10% volume they quote.
  idle capacity      how far the operating margin sits below its own best year
                     in the provider's history. A business at peak margin has
                     already spent its torque.
  demand arriving    forward revenue over trailing. Torque is worth nothing
                     until volume comes back.
  survival           net debt over EBITDA. Their thesis is that the cycle may
                     not return; this desk is not paid to find out at a
                     leverage that would not survive it if it did.

Points 4 and 5 are not computable at the company level, and this screen does
not pretend otherwise. Price sensitivity is a property of *who buys*, and
Cambrian's own estimate of it is per buyer group, not per company: memory's
buyers start cutting volume at a +15-25% price rise on roughly half of demand,
wafer buyers only at +50-140% on about a twentieth. Those figures are shown
on the thesis panel as Cambrian's estimates, by segment, and are deliberately
not turned into a score here — a segment prior copied onto every company in
the segment would rank nothing and would look like it did.

THE TENSION WITH THIS DESK'S OWN PRINCIPLES

`principles.no-commodity-price-takers` says this desk will not own a business
whose earnings are set by a price it does not control. Spot-priced memory is
that business by definition, and Cambrian likes it *because* of the spot price:
the marginal buyer sets the price for the whole pool. The two views are
reconcilable only if Cambrian's point 4 holds — that the buyer, not the cycle,
now sets the price. That is a judgment, so the screen does not resolve it; the
`price_taker_tension` flag marks every memory row so the conflict is read
rather than discovered.

THE CAPITAL-CYCLE COUNTER-THESIS

Hosking Partners' Q3 2026 note reads the same industry the other way: it is
still selling memory, because the profits are "super-normal" and capital is
arriving. Each row carries `data/capital_cycle.py`'s reading — capex against
depreciation, its direction, the margin against its own average, share
issuance — and `capital_arriving` when the signals agree. On the October 2026
accounts SK hynix ran capex at 2.1x depreciation with a margin 30 points above
its own average, while SUMCO and Siltronic were back to replacing what wears
out at margins below theirs: the two theses agree on wafers and disagree on
memory. Shown, not scored, for the same reason the tension flag is.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import yfinance as yf

from hedge_fund.screeners import principles

logger = logging.getLogger(__name__)

#: --- The universe, by segment -----------------------------------------
#:
#: Curated, not scraped, and that is a choice rather than a gap. There is no
#: index of "AI supply-chain oligopolies"; the segments are Cambrian's own
#: chart, and the membership is every listed maker Yahoo prices in each.
#: Software and fabless names are included on purpose: they fail the
#: physical-supply-chain filter, but their multiples are what the segment
#: dot plot compares against, which is the whole of Cambrian's first chart.
#:
#: `(segment, note)`. The note marks a business where the segment is only
#: part of revenue, because a conglomerate's multiple is not the segment's.
SEGMENT_BY_TICKER: dict[str, tuple[str, str | None]] = {
    # Silicon wafers and engineered substrates
    "3436.T": ("wafers", None),  # SUMCO
    "4063.T": ("wafers", "Chemicals group; wafers are roughly a third of profit"),  # Shin-Etsu
    "6488.TWO": ("wafers", None),  # GlobalWafers
    "WAF.DE": ("wafers", None),  # Siltronic
    "SOI.PA": ("wafers", "Engineered SOI substrates, not prime polished wafers"),  # Soitec
    "3445.T": ("wafers", "Wafer reclaim, the cheapest segment on Cambrian's chart"),  # RS Tech
    # Memory
    "000660.KS": ("memory", None),  # SK hynix
    "005930.KS": ("memory", "Also phones, displays and foundry"),  # Samsung Electronics
    "MU": ("memory", None),
    "285A.T": ("memory", None),  # Kioxia
    "SNDK": ("memory", None),  # Sandisk
    "2408.TW": ("memory", None),  # Nanya
    "2344.TW": ("memory", None),  # Winbond
    # Multilayer ceramic capacitors
    "6981.T": ("capacitors", None),  # Murata
    "009150.KS": ("capacitors", "Also camera modules and substrates"),  # Samsung Electro-Mechanics
    "6976.T": ("capacitors", None),  # Taiyo Yuden
    "2327.TW": ("capacitors", None),  # Yageo
    "6762.T": ("capacitors", "Mostly batteries; MLCCs are a minority"),  # TDK
    "6971.T": ("capacitors", "Conglomerate; components are one segment"),  # Kyocera
    # Chip factories
    "2330.TW": ("foundries", None),  # TSMC, local line — the ADR reports in TWD
    "2303.TW": ("foundries", None),  # UMC, local line for the same reason
    "GFS": ("foundries", None),
    "0981.HK": ("foundries", None),  # SMIC
    "1347.HK": ("foundries", None),  # Hua Hong
    "TSEM": ("foundries", None),
    "5347.TWO": ("foundries", None),  # Vanguard International
    # Contrast: fabless designers — semiconductors with no factories
    "NVDA": ("fabless", None),
    "AMD": ("fabless", None),
    "AVGO": ("fabless", None),
    "QCOM": ("fabless", None),
    "2454.TW": ("fabless", None),  # MediaTek
    # Contrast: large public software, Cambrian's comparison set
    "PLTR": ("software", None),
    "SNOW": ("software", None),
    "CRWD": ("software", None),
    "NET": ("software", None),
    "NOW": ("software", None),
    "DDOG": ("software", None),
}

#: Segments that are the thesis. Everything else is there to be compared to.
PHYSICAL_SEGMENTS: tuple[str, ...] = ("wafers", "memory", "capacitors", "foundries")

#: For a name outside the curated list — the screen run on another universe —
#: the industry label decides whether it is physical supply chain. Coarse by
#: admission: "Semiconductors" includes every fabless designer, which is what
#: the plant filter below is for.
PHYSICAL_INDUSTRIES: tuple[str, ...] = (
    "semiconductors",
    "semiconductor equipment & materials",
    "electronic components",
)

#: --- Hard filters ------------------------------------------------------
#:
#: Net plant over annual revenue. Calibrated on the curated list, October
#: 2026: makers run 0.37 (Kyocera) to 0.82 (SK hynix); the fabless designers
#: 0.04 (Broadcom) to 0.12 (MediaTek). Revenue quadrupling in a memory boom
#: shrinks the ratio, and SK hynix still clears it four times over.
MIN_PPE_TO_REVENUE = 0.20

#: Makers whose plant is real but not on their own balance sheet, with why.
#: Exempt from the plant test by name rather than by a looser threshold,
#: which would let the fabless designers back in.
PLANT_OFF_BALANCE_SHEET: dict[str, str] = {
    "SNDK": "Fabs held through the Flash Ventures joint venture with Kioxia",
}

#: --- Scoring anchors (best, worst) ---------------------------------------
#:
#: Market cap over forward revenue. Cambrian's chart puts the physical
#: segments at 3-6x and software at 9-100x. Full marks at 2x, nothing at 8x.
MULTIPLE_BEST = 2.0
MULTIPLE_WORST = 8.0

#: Degree of operating leverage. Their illustration is 4.7.
TORQUE_BEST = 5.0
TORQUE_WORST = 1.5

#: Percentage points the operating margin sits below its best year on record.
IDLE_GAP_BEST_PP = 15.0
IDLE_GAP_WORST_PP = 0.0

#: Forward revenue over trailing, minus one.
DEMAND_BEST = 0.25
DEMAND_WORST = 0.0

#: Net debt over EBITDA. Net cash is full marks.
LEVERAGE_BEST = 0.0
LEVERAGE_WORST = 3.0

#: Points per component, out of 100. The multiple carries the most because it
#: is the thesis's first claim and the one their whole first chart is about.
WEIGHTS: dict[str, float] = {
    "cheap_on_revenue": 35.0,
    "torque": 20.0,
    "idle_capacity": 15.0,
    "demand_arriving": 15.0,
    "survives_a_cycle": 15.0,
}

#: Said on every row, scored on none of them.
UNCHECKABLE_BY_DESIGN: tuple[str, ...] = (
    "whether this company's customers are price-inelastic — Cambrian estimates it by buyer group, not by company",
    "real fab or line utilisation, which no feed carries; the margin gap is a proxy",
    "whether supply really cannot scale, including Chinese capacity and announced capex",
    "the AI timeline itself — the thesis is an explicit bet that demand keeps growing fast",
    "how much of revenue is actually the segment, for the groups marked mixed",
)


@dataclass
class ScarcitySnapshot:
    ticker: str
    name: str | None = None
    segment: str | None = None
    segment_note: str | None = None
    quote_currency: str | None = None
    financial_currency: str | None = None
    fx_rate: float | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    revenue_ttm: float | None = None
    revenue_ntm: float | None = None
    multiple_basis: str | None = None
    revenue_multiple: float | None = None
    ppe_to_revenue: float | None = None
    operating_margin: float | None = None
    peak_operating_margin: float | None = None
    idle_gap_pp: float | None = None
    torque: float | None = None
    torque_unmeasured_reason: str | None = None
    demand_growth: float | None = None
    net_debt_to_ebitda: float | None = None
    #: Capital-cycle reading from the annual statements. Shown, never scored:
    #: it is the counter-thesis, and a screen that quietly weighted it would
    #: be neither Cambrian's nor Hosking's.
    capital_cycle: dict[str, Any] | None = None
    years_of_history: int = 0
    error: str | None = None


@dataclass
class ScarcityResult:
    ticker: str
    passed: bool = False
    failures: list[str] = field(default_factory=list)
    composite: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)
    price_taker_tension: bool = False
    capital_arriving: bool = False
    snapshot: dict[str, Any] = field(default_factory=dict)
    unchecked: tuple[str, ...] = UNCHECKABLE_BY_DESIGN
    error: str | None = None


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _ramp(value: float | None, best: float, worst: float, points: float) -> float:
    """Linear score between two anchors, in whichever direction they imply."""
    if value is None:
        return 0.0
    lo, hi = sorted((best, worst))
    v = min(max(value, lo), hi)
    return points * (v - worst) / (best - worst)


def _row_series(df: Any, *keys: str) -> list[float]:
    """Newest-first values of the first matching statement row, gaps dropped."""
    if df is None or getattr(df, "empty", True):
        return []
    for k in keys:
        if k in df.index:
            return [x for x in (_f(v) for v in df.loc[k].tolist()) if x is not None]
    return []


def _fx(from_ccy: str, to_ccy: str) -> float | None:
    """A quoted rate, never an invented one. None when Yahoo has no pair."""
    try:
        hist = yf.Ticker(f"{from_ccy}{to_ccy}=X").history(period="5d")
        if hist is not None and not hist.empty:
            return _f(hist["Close"].dropna().iloc[-1])
    except Exception as exc:  # noqa: BLE001
        logger.debug("fx %s->%s failed: %s", from_ccy, to_ccy, exc)
    return None


def calendarise(
    fy0: float | None, fy1: float | None, last_fy_end: float | None, now: float
) -> float | None:
    """Next-twelve-month revenue from two fiscal-year estimates.

    The share of the current fiscal year still to run comes from FY0, the
    rest from FY1 — the standard calendarisation. Without a fiscal year end
    the next year alone is used, which is the closer of the two to "forward".
    """
    if fy0 is None or fy1 is None or fy0 <= 0 or fy1 <= 0:
        return None
    if last_fy_end is None:
        return fy1
    year = 365.25 * 86_400
    remaining = min(max((last_fy_end + year - now) / year, 0.0), 1.0)
    return remaining * fy0 + (1 - remaining) * fy1


def torque_of(
    gross_profit: float | None, d_and_a: float | None, ebit: float | None
) -> tuple[float | None, str | None]:
    """Degree of operating leverage, or None with the reason it was refused.

    DOL = contribution / EBIT, and with depreciation and operating expense
    treated as fixed, contribution is gross profit plus the depreciation
    inside cost of goods. A loss-making business has undefined torque, not
    infinite torque — refused rather than scored as best, which would put
    every company losing money at the top of the list.
    """
    if gross_profit is None or ebit is None:
        return None, "missing_statements"
    if ebit <= 0:
        return None, "operating_loss"
    return (gross_profit + max(d_and_a or 0.0, 0.0)) / ebit, None


def fetch_scarcity_snapshot(ticker: str) -> ScarcitySnapshot:
    sym = ticker.strip().upper()
    snap = ScarcitySnapshot(ticker=sym)
    seg = SEGMENT_BY_TICKER.get(sym)
    if seg:
        snap.segment, snap.segment_note = seg
    t = yf.Ticker(sym)
    try:
        info = t.info or {}
        if not info or (
            info.get("regularMarketPrice") is None and info.get("currentPrice") is None
        ):
            snap.error = "no_quote_or_info"
            return snap

        snap.name = info.get("shortName") or info.get("longName")
        snap.sector = info.get("sector")
        snap.industry = info.get("industry")
        snap.quote_currency = (info.get("currency") or "").upper() or None
        snap.financial_currency = (
            info.get("financialCurrency") or ""
        ).upper() or snap.quote_currency
        snap.operating_margin = _f(info.get("operatingMargins"))
        snap.revenue_ttm = _f(info.get("totalRevenue"))

        # Every flow figure below is in the reporting currency. The market cap
        # is in the quote currency. When they differ — SMIC and Hua Hong quote
        # in HKD and report in USD — the provider's own enterpriseToRevenue is
        # off by the exchange rate (44x for SMIC, against roughly 5x), so the
        # cap is converted at a quoted rate or the multiple is refused.
        cap = _f(info.get("marketCap"))
        if (
            cap is not None
            and snap.quote_currency
            and snap.financial_currency != snap.quote_currency
        ):
            rate = _fx(snap.quote_currency, snap.financial_currency or "")
            snap.fx_rate = rate
            cap = cap * rate if rate else None
        snap.market_cap = cap

        try:
            est = t.revenue_estimate
            fy0 = _f(est.loc["0y", "avg"]) if est is not None and "0y" in est.index else None
            fy1 = _f(est.loc["+1y", "avg"]) if est is not None and "+1y" in est.index else None
        except Exception:  # noqa: BLE001 — estimates are optional
            fy0 = fy1 = None
        snap.revenue_ntm = calendarise(fy0, fy1, _f(info.get("lastFiscalYearEnd")), time.time())
        base = snap.revenue_ntm or snap.revenue_ttm
        snap.multiple_basis = "forward" if snap.revenue_ntm else ("trailing" if base else None)
        if snap.market_cap is not None and base:
            snap.revenue_multiple = snap.market_cap / base
        if snap.revenue_ntm and snap.revenue_ttm:
            snap.demand_growth = snap.revenue_ntm / snap.revenue_ttm - 1

        inc, cf, bs = t.income_stmt, t.cashflow, t.balance_sheet
        revs = _row_series(inc, "Total Revenue", "Operating Revenue")
        ebits = _row_series(inc, "Operating Income", "EBIT")
        gp = _row_series(inc, "Gross Profit")
        da = _row_series(cf, "Depreciation And Amortization", "Depreciation Amortization Depletion")
        snap.years_of_history = min(len(revs), len(ebits))
        margins = [e / r for e, r in zip(ebits, revs, strict=False) if r > 0]
        if margins:
            current = snap.operating_margin if snap.operating_margin is not None else margins[0]
            snap.peak_operating_margin = max(margins + [current])
            snap.idle_gap_pp = (snap.peak_operating_margin - current) * 100
        snap.torque, snap.torque_unmeasured_reason = torque_of(
            gp[0] if gp else None, da[0] if da else None, ebits[0] if ebits else None
        )

        from hedge_fund.data.capital_cycle import read as read_cycle
        from hedge_fund.data.statements import fetch_statements

        snap.capital_cycle = read_cycle(fetch_statements(sym))

        ppe = _row_series(bs, "Net PPE")
        if ppe and revs and revs[0] > 0:
            snap.ppe_to_revenue = ppe[0] / revs[0]

        ebitda = _f(info.get("ebitda"))
        if ebitda and ebitda > 0:
            debt = _f(info.get("totalDebt")) or 0.0
            cash = _f(info.get("totalCash")) or 0.0
            snap.net_debt_to_ebitda = (debt - cash) / ebitda
    except Exception as exc:  # noqa: BLE001 — one bad name must not stop a run
        logger.debug("scarcity snapshot for %s failed: %s", sym, exc)
        snap.error = f"fetch_failed: {type(exc).__name__}"
    return snap


def is_physical(snap: ScarcitySnapshot) -> bool:
    if snap.segment:
        return snap.segment in PHYSICAL_SEGMENTS
    low = (snap.industry or "").lower()
    return any(k == low or k in low for k in PHYSICAL_INDUSTRIES)


def evaluate(snap: ScarcitySnapshot) -> ScarcityResult:
    r = ScarcityResult(ticker=snap.ticker)
    r.snapshot = {k: v for k, v in snap.__dict__.items() if k != "error"}
    if snap.error:
        r.error = snap.error
        r.failures.append("fetch_error")
        return r

    fails = r.failures
    excl = principles.excluded_by(snap.sector, snap.industry)
    if excl:
        fails.append(f"excluded:{excl}")
    if not is_physical(snap):
        fails.append("not_physical_supply_chain")
    if snap.ticker in PLANT_OFF_BALANCE_SHEET:
        pass
    elif snap.ppe_to_revenue is None:
        fails.append("plant_not_reported")
    elif snap.ppe_to_revenue < MIN_PPE_TO_REVENUE:
        fails.append("no_factories")
    if snap.revenue_multiple is None:
        fails.append(
            "currency_not_convertible"
            if snap.quote_currency != snap.financial_currency and snap.fx_rate is None
            else "missing_revenue_multiple"
        )

    r.price_taker_tension = snap.segment == "memory"
    r.capital_arriving = (snap.capital_cycle or {}).get("capital_cycle") == "arriving"
    r.passed = not fails
    if not r.passed:
        return r

    w = WEIGHTS
    s = r.scores
    s["cheap_on_revenue"] = _ramp(
        snap.revenue_multiple, MULTIPLE_BEST, MULTIPLE_WORST, w["cheap_on_revenue"]
    )
    # Unmeasured torque scores at the midpoint: a loss-maker is neither the
    # most levered business on the list nor the least.
    s["torque"] = (
        _ramp(snap.torque, TORQUE_BEST, TORQUE_WORST, w["torque"])
        if snap.torque is not None
        else w["torque"] / 2
    )
    s["idle_capacity"] = _ramp(
        snap.idle_gap_pp, IDLE_GAP_BEST_PP, IDLE_GAP_WORST_PP, w["idle_capacity"]
    )
    s["demand_arriving"] = _ramp(
        snap.demand_growth, DEMAND_BEST, DEMAND_WORST, w["demand_arriving"]
    )
    s["survives_a_cycle"] = _ramp(
        snap.net_debt_to_ebitda, LEVERAGE_BEST, LEVERAGE_WORST, w["survives_a_cycle"]
    )
    for k in s:
        s[k] = round(s[k], 2)
    r.composite = round(sum(s.values()), 1)
    return r


def _row(r: ScarcityResult) -> dict[str, Any]:
    return {
        "ticker": r.ticker,
        "passed": r.passed,
        "failures": r.failures,
        "composite": r.composite,
        "scores": r.scores,
        "price_taker_tension": r.price_taker_tension,
        "capital_arriving": r.capital_arriving,
        "snapshot": r.snapshot,
        "unchecked": list(r.unchecked),
        "error": r.error,
    }


def run_cambrian_scarcity_for_ticker(ticker: str) -> dict[str, Any]:
    return _row(evaluate(fetch_scarcity_snapshot(ticker)))


def fetch_ai_supply_chain() -> list[str]:
    """The curated universe: every segment, contrasts included."""
    return list(SEGMENT_BY_TICKER)
