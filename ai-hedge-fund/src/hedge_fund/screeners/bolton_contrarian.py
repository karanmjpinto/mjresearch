"""
Bolton contrarian / special-situations screener — hard filters + 5-part score (/100).

Anthony Bolton ran Fidelity Special Situations for 28 years looking for the same
shape: a company the market has given up on, where something specific is about
to change the story. His framework has five sections, and only four of them can
be computed:

    valuation        cheap on its own history and against peers
    neglect          unloved — near lows, shorted, uncovered, being sold
    catalyst         a reason the story re-rates          <- NOT COMPUTED
    balance sheet    strong enough to survive the wait
    technicals       stabilising rather than still falling

The catalyst section is the one he says separates a re-rating from a value trap,
and it is exactly the part no data feed carries: spin-offs, restructurings,
legal overhangs lifting, an asset worth more than the whole company. Those need
reading, not arithmetic.

So this screen deliberately does not score them, and does not pretend to. Every
row carries `catalyst_checked: False` and the honest consequence: **a name that
passes this screen is cheap, unloved and solvent, which by Bolton's own
reasoning is a value trap until someone finds the catalyst.** That judgment is
the `anthony_bolton` persona's job on the research page, which is why the
screen's output links there rather than ending in a verdict.

Data via yfinance. Verify against filings before acting on any of it.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import yfinance as yf

from hedge_fund.screeners.yartseva import _f, _sum_q

logger = logging.getLogger(__name__)

# --- Hard filters -------------------------------------------------------
# Loose on purpose. Bolton bought turnarounds, so a screen that demands
# healthy current earnings would reject the very companies he was hunting.
# These only establish "cheap on something, solvent enough to wait, and not
# already loved" — the ranking does the discriminating.

#: Below this, the spread and the disclosure make the exercise academic.
MIN_MARKET_CAP = 300_000_000

#: At least one of these must hold. A stock has to be cheap on *some*
#: recognised measure to be in a contrarian screen at all; requiring all four
#: would demand a company simultaneously cheap on earnings it does not
#: currently have.
CHEAP_PE = 15.0
CHEAP_PB = 1.5
CHEAP_EV_EBITDA = 9.0
CHEAP_P_FCF = 15.0

#: Survive-the-wait floor. His stated preference is debt/equity under 1.0 and
#: interest cover above 3x; those are scored, not required, because a
#: deleveraging story is a legitimate Bolton setup and would fail its own
#: entry test on the day it becomes interesting.
MAX_DEBT_TO_EQUITY_HARD = 2.5
MIN_INTEREST_COVER_HARD = 1.5

#: "Unloved" as a number: how far up off the 52-week low the price still is,
#: as a fraction of the 52-week range. 0 = at the low, 1 = at the high.
MAX_RANGE_POSITION = 0.60

# --- Scored preferences (his stated thresholds) -------------------------
PREF_DEBT_TO_EQUITY = 1.0
PREF_INTEREST_COVER = 3.0
PREF_SHORT_INTEREST = 0.10
#: "Low analyst coverage" — few enough that the price is not a consensus.
LOW_ANALYST_COVERAGE = 8

#: How far back an insider purchase still counts as a signal of confidence.
INSIDER_LOOKBACK_DAYS = 365


@dataclass
class BoltonSnapshot:
    ticker: str
    market_cap: float | None = None
    sector: str | None = None
    price_current: float | None = None
    price_52w_high: float | None = None
    price_52w_low: float | None = None
    trailing_pe: float | None = None
    price_to_book: float | None = None
    ev_to_ebitda: float | None = None
    free_cash_flow_ttm: float | None = None
    operating_cash_flow_ttm: float | None = None
    net_income_ttm: float | None = None
    ebit_ttm: float | None = None
    interest_expense_ttm: float | None = None
    debt_to_equity: float | None = None
    short_percent_float: float | None = None
    analyst_count: int | None = None
    held_percent_institutions: float | None = None
    insider_buys_12m: int = 0
    insider_sells_12m: int = 0
    return_6m_pct: float | None = None
    return_1m_pct: float | None = None
    error: str | None = None


def fetch_bolton_snapshot(ticker: str) -> BoltonSnapshot:
    t = yf.Ticker(ticker.strip().upper())
    snap = BoltonSnapshot(ticker=ticker.strip().upper())
    try:
        info = t.info or {}
        if not info or (
            info.get("regularMarketPrice") is None and info.get("currentPrice") is None
        ):
            snap.error = "no_quote_or_info"
            return snap

        snap.market_cap = _f(info.get("marketCap"))
        snap.sector = info.get("sector") or info.get("industry") or None
        snap.price_current = _f(info.get("currentPrice") or info.get("regularMarketPrice"))
        snap.price_52w_high = _f(info.get("fiftyTwoWeekHigh"))
        snap.price_52w_low = _f(info.get("fiftyTwoWeekLow"))
        snap.trailing_pe = _f(info.get("trailingPE"))
        snap.price_to_book = _f(info.get("priceToBook"))
        snap.ev_to_ebitda = _f(info.get("enterpriseToEbitda"))
        snap.short_percent_float = _f(info.get("shortPercentOfFloat"))
        snap.held_percent_institutions = _f(info.get("heldPercentInstitutions"))
        dte = _f(info.get("debtToEquity"))
        # yfinance reports this as a percentage (154.06 meaning 1.54x).
        snap.debt_to_equity = dte / 100 if dte is not None else None
        n = info.get("numberOfAnalystOpinions")
        snap.analyst_count = int(n) if isinstance(n, (int, float)) and n >= 0 else None

        q_inc = t.quarterly_income_stmt
        q_cf = t.quarterly_cashflow
        snap.free_cash_flow_ttm = _sum_q(q_cf, "Free Cash Flow", 0, 4)
        snap.operating_cash_flow_ttm = _sum_q(q_cf, "Operating Cash Flow", 0, 4)
        snap.net_income_ttm = _sum_q(q_inc, "Net Income", 0, 4)
        snap.ebit_ttm = _sum_q(q_inc, "EBIT", 0, 4) or _sum_q(q_inc, "Operating Income", 0, 4)
        interest = _sum_q(q_inc, "Interest Expense", 0, 4)
        snap.interest_expense_ttm = abs(interest) if interest is not None else None

        snap.insider_buys_12m, snap.insider_sells_12m = _insider_counts(t)

        try:
            hist = t.history(period="400d", interval="1d")
        except Exception as exc:  # noqa: BLE001
            hist = pd.DataFrame()
            logger.warning("%s: no price history (%s)", snap.ticker, exc)
        if not hist.empty and "Close" in hist.columns:
            close = hist["Close"].dropna()
            if len(close) >= 2:
                last = float(close.iloc[-1])
                for attr, back in (("return_6m_pct", 126), ("return_1m_pct", 21)):
                    prior = float(close.iloc[max(0, len(close) - back)])
                    if prior > 0:
                        setattr(snap, attr, (last - prior) / prior * 100)
            if snap.price_52w_high is None or snap.price_52w_low is None:
                window = close.tail(252)
                if len(window) > 20:
                    snap.price_52w_high = float(window.max())
                    snap.price_52w_low = float(window.min())

        return snap
    except Exception as exc:  # noqa: BLE001
        snap.error = str(exc)
        return snap


def _insider_counts(t: yf.Ticker) -> tuple[int, int]:
    """Insider purchases and sales in the last year.

    Counted, not summed in dollars. Bolton's checklist asks whether insiders
    are buying or selling — a signal of confidence, not of magnitude — and one
    large option-exercise sale would otherwise swamp a dozen open-market
    purchases and invert the reading.
    """
    try:
        df = t.insider_transactions
    except Exception:  # noqa: BLE001
        return 0, 0
    if df is None or df.empty:
        return 0, 0

    cols = {str(c).lower(): c for c in df.columns}
    text_col = cols.get("text") or cols.get("transaction")
    date_col = cols.get("start date") or cols.get("date")
    if text_col is None:
        return 0, 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=INSIDER_LOOKBACK_DAYS)
    buys = sells = 0
    for _, row in df.iterrows():
        if date_col is not None:
            when = pd.to_datetime(row.get(date_col), errors="coerce", utc=True)
            if pd.isna(when) or when < cutoff:
                continue
        label = str(row.get(text_col) or "").lower()
        # "Purchase" / "Sale" are yfinance's wording. Option exercises and
        # awards are neither: they say nothing about conviction at this price.
        if "purchase" in label or label.startswith("buy"):
            buys += 1
        elif "sale" in label or "sold" in label:
            sells += 1
    return buys, sells


@dataclass
class BoltonResult:
    ticker: str
    passed: bool = False
    composite: float | None = None
    tier: str | None = None
    failures: list[str] = field(default_factory=list)

    valuation_score: float = 0.0
    neglect_score: float = 0.0
    balance_sheet_score: float = 0.0
    insider_score: float = 0.0
    stabilisation_score: float = 0.0

    cheap_on: list[str] = field(default_factory=list)
    range_position: float | None = None
    short_percent_float: float | None = None
    analyst_count: int | None = None
    debt_to_equity: float | None = None
    interest_cover: float | None = None
    cash_conversion: float | None = None
    insider_net_12m: int = 0
    trailing_pe: float | None = None
    price_to_book: float | None = None
    ev_to_ebitda: float | None = None
    p_fcf: float | None = None

    #: Always False. The screen cannot see catalysts; see the module docstring.
    catalyst_checked: bool = False
    snapshot: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def _band(value: float | None, best: float, worst: float, points: float) -> float:
    """Linear score between two thresholds, clamped.

    `best` may be below or above `worst`, so one helper covers "lower is
    better" (P/E) and "higher is better" (interest cover) without a flag.
    """
    if value is None:
        return 0.0
    if best == worst:
        return points if value == best else 0.0
    frac = (worst - value) / (worst - best)
    return points * max(0.0, min(1.0, frac))


def score_bolton_contrarian(snap: BoltonSnapshot) -> BoltonResult:
    r = BoltonResult(ticker=snap.ticker)
    if snap.error:
        r.error = snap.error
        return r

    r.snapshot = {k: v for k, v in asdict(snap).items() if k not in {"ticker", "error"}}

    fcf = snap.free_cash_flow_ttm
    r.trailing_pe = snap.trailing_pe
    r.price_to_book = snap.price_to_book
    r.ev_to_ebitda = snap.ev_to_ebitda
    r.p_fcf = _ratio(snap.market_cap, fcf) if fcf and fcf > 0 else None
    r.debt_to_equity = snap.debt_to_equity
    r.interest_cover = _ratio(snap.ebit_ttm, snap.interest_expense_ttm)
    r.cash_conversion = _ratio(snap.operating_cash_flow_ttm, snap.net_income_ttm)
    r.short_percent_float = snap.short_percent_float
    r.analyst_count = snap.analyst_count
    r.insider_net_12m = snap.insider_buys_12m - snap.insider_sells_12m

    # Where in its own 52-week range the price sits. The screen's definition of
    # "unloved" — an absolute price says nothing, the position in the range
    # says the market has marked it down and left it there.
    hi, lo, px = snap.price_52w_high, snap.price_52w_low, snap.price_current
    if hi is not None and lo is not None and px is not None and hi > lo:
        r.range_position = (px - lo) / (hi - lo)

    # ---- Hard filters ----
    fails: list[str] = []

    if snap.market_cap is None or snap.market_cap < MIN_MARKET_CAP:
        fails.append("market_cap_below_floor")

    cheap: list[str] = []
    if r.trailing_pe is not None and 0 < r.trailing_pe < CHEAP_PE:
        cheap.append(f"P/E {r.trailing_pe:.1f}")
    if r.price_to_book is not None and 0 < r.price_to_book < CHEAP_PB:
        cheap.append(f"P/B {r.price_to_book:.2f}")
    if r.ev_to_ebitda is not None and 0 < r.ev_to_ebitda < CHEAP_EV_EBITDA:
        cheap.append(f"EV/EBITDA {r.ev_to_ebitda:.1f}")
    if r.p_fcf is not None and 0 < r.p_fcf < CHEAP_P_FCF:
        cheap.append(f"P/FCF {r.p_fcf:.1f}")
    r.cheap_on = cheap
    if not cheap:
        fails.append("not_cheap_on_any_measure")

    if r.range_position is None:
        fails.append("no_52w_range")
    elif r.range_position > MAX_RANGE_POSITION:
        fails.append("not_out_of_favour")

    if snap.operating_cash_flow_ttm is None or snap.operating_cash_flow_ttm <= 0:
        fails.append("no_operating_cash_flow")

    if r.debt_to_equity is not None and r.debt_to_equity > MAX_DEBT_TO_EQUITY_HARD:
        fails.append("leverage_above_ceiling")

    # Absent interest expense means no meaningful debt service, which passes.
    if (
        snap.interest_expense_ttm
        and r.interest_cover is not None
        and r.interest_cover < MIN_INTEREST_COVER_HARD
    ):
        fails.append("interest_cover_below_floor")

    r.failures = fails
    r.passed = not fails

    # ---- Score, computed for every name that returned data ----
    # Valuation, 30. Each measure contributes only if present, and the total is
    # rescaled by how many were available — otherwise a company with no P/E
    # looks worse than one with a bad P/E.
    val_parts: list[float] = []
    if r.trailing_pe is not None and r.trailing_pe > 0:
        val_parts.append(_band(r.trailing_pe, 5.0, 20.0, 1.0))
    if r.price_to_book is not None and r.price_to_book > 0:
        val_parts.append(_band(r.price_to_book, 0.4, 2.0, 1.0))
    if r.ev_to_ebitda is not None and r.ev_to_ebitda > 0:
        val_parts.append(_band(r.ev_to_ebitda, 3.0, 10.0, 1.0))
    if r.p_fcf is not None and r.p_fcf > 0:
        val_parts.append(_band(r.p_fcf, 5.0, 18.0, 1.0))
    r.valuation_score = 30.0 * (sum(val_parts) / len(val_parts)) if val_parts else 0.0

    # Neglect, 25. How thoroughly the market has walked away.
    neg = 0.0
    neg += _band(r.range_position, 0.0, 0.8, 12.0)
    if r.short_percent_float is not None:
        # Heavily shorted is a Bolton signal, not a disqualifier — the squeeze
        # is part of the re-rating. Beyond a quarter of the float it stops
        # adding information and starts describing a solvency bet.
        neg += min(6.0, (r.short_percent_float / PREF_SHORT_INTEREST) * 3.0)
    if r.analyst_count is not None:
        neg += _band(float(r.analyst_count), 0.0, float(LOW_ANALYST_COVERAGE) * 2, 4.0)
    if snap.held_percent_institutions is not None:
        neg += _band(snap.held_percent_institutions, 0.30, 0.95, 3.0)
    r.neglect_score = min(25.0, neg)

    # Balance sheet, 20. Can it survive long enough for the story to change.
    bs = 0.0
    bs += _band(r.debt_to_equity, 0.0, PREF_DEBT_TO_EQUITY * 2, 8.0)
    if snap.interest_expense_ttm:
        bs += _band(r.interest_cover, PREF_INTEREST_COVER * 3, PREF_INTEREST_COVER, 7.0)
    else:
        bs += 7.0  # no debt service to cover
    if r.cash_conversion is not None:
        # Bolton's earnings-quality test: cash running ahead of reported
        # profit. Capped, because a huge ratio usually means a tiny
        # denominator rather than exceptional quality.
        bs += min(5.0, max(0.0, r.cash_conversion) * 2.5)
    r.balance_sheet_score = min(20.0, bs)

    # Insider conviction, 15.
    if r.insider_net_12m > 0:
        r.insider_score = min(15.0, 7.0 + r.insider_net_12m * 2.0)
    elif r.insider_net_12m == 0 and snap.insider_buys_12m == 0:
        r.insider_score = 5.0  # no signal either way
    else:
        r.insider_score = max(0.0, 5.0 + r.insider_net_12m)

    # Stabilisation, 10. His last section: down, but no longer falling. A
    # stock still in free-fall is a cheaper stock tomorrow.
    stab = 0.0
    if snap.return_1m_pct is not None:
        stab += _band(snap.return_1m_pct, 10.0, -20.0, 6.0)
    if snap.return_6m_pct is not None and snap.return_1m_pct is not None:
        # Improving on the month against the half-year is the turn he wants.
        if snap.return_1m_pct > snap.return_6m_pct / 6:
            stab += 4.0
    r.stabilisation_score = min(10.0, stab)

    r.composite = round(
        r.valuation_score
        + r.neglect_score
        + r.balance_sheet_score
        + r.insider_score
        + r.stabilisation_score,
        2,
    )
    r.tier = (
        "strong"
        if r.composite >= 70
        else "watch"
        if r.composite >= 55
        else "borderline"
        if r.composite >= 40
        else "fail"
    )
    return r


def run_bolton_contrarian_for_ticker(ticker: str) -> dict[str, Any]:
    snap = fetch_bolton_snapshot(ticker)
    return score_bolton_contrarian(snap).to_dict()
