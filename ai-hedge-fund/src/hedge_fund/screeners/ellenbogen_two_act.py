"""
Ellenbogen two-act screener — the compounder signature, and the hole where the
second act goes.

Henry Ellenbogen ran T. Rowe Price New Horizons from 2010 to 2018 at 19.2% a
year, beating the S&P 500, the Russell 2000 Growth and his peers by over 5%
annually while managing the largest pool of small-cap money in America. Two
numbers from that run are the whole reason this screen exists:

    over 90% of his alpha came from 20 compounders
    all of it came from companies he had owned for more than four years

He found those twenty by reading fifty years of New Horizons shareholder
letters and then the history of the US market, and arriving at an arithmetic
fact: in any rolling ten-year period, out of roughly 4,000 listed companies,
about **40 compound wealth at 20% a year**. One percent. Roughly 80% of them
begin that journey as small caps, which is the shelf this screen is pointed at.
Durable's own study of the small-cap cohort puts it at a median of 28 names a
year, about 2.4% of eligible companies, and credits an annual cohort with
nearly 35% of the market's total appreciation.

**What his framework says a compounder looks like.** Anouk Dey's study, which
he commissioned and which became the firm's method, found two traits:

    increasing returns on invested capital   they got better as they got
                                             bigger, faced less competition as
                                             they gained scale, and could
                                             reinvest at persistently high
                                             rates
    structural volatility                    over the ten years they compounded
                                             at 20%, in one of those years they
                                             fell 62% — usually not in a crash,
                                             but during a transition

The first is computable, and it is the part this screen is actually built
around. Note what it is *not*: a high return on capital. A static 30% ROIC on a
business that has not grown is a good business, not a compounder. The test is
the slope — returns rising while the business gets bigger — and separating
those two is most of the work below.

**The two acts, and why half of this screen is missing.** He thinks of a
company in two acts. Act 1 is product-market fit, a large addressable market,
and unit economics that work. Act 2 is the leap: a significant new product, a
major new market, becoming something fundamentally larger than the original
business. Netflix's Act 1 was DVD-by-mail; Act 2 was streaming, and between
them sat 800,000 cancellations and a 75% fall. Rackspace went into the same
kind of transition against AWS and never came out.

In his words: "The trick was in distinguishing between a company failing and a
company transitioning, then having the conviction to hold through the
difference."

**That distinction is not in any data feed, and this screen does not make it.**
Act 1 leaves a financial trace — growth, a profitable core, returns on capital
that rise with scale — and the trace is what is scored here. Act 2 is a
judgment about a product that does not exist yet, a market nobody has entered,
and a management team's appetite for a hard transition. Every row carries
`act2_checked: False` and `founder_act2_checked: False`, and the honest
consequence is this: **a name that passes this screen has the financial
signature of an Act 1 company. Whether it has a second act is the entire
question, and the screen has not answered any part of it.** That is the
`henry_ellenbogen` persona's job on the research page.

**The drawdown is reported and deliberately not scored.** His most distinctive
claim is that the 62% fall is structural rather than bad luck — the moment the
compounder is made or lost, and the moment he bought more. Scoring it would be
a mistake twice over: it would turn a quality screen into a falling-knife
screen, and it would assert the one thing he says a human has to decide. So the
drawdown from the five-year high is carried as a fact beside the score, and a
name that is financially intact *and* down 40% is flagged as
`transition_candidate` — which means "this is where the question gets asked",
not "buy it".

**One place where this desk overrules him.** His own book held software names
that funded themselves with stock, heavily. This desk's standing principle is
that it will not own a business which funds itself by issuing shares to the
holder, so the dilution ceiling here is real and some of his actual positions
would fail it. Recorded rather than quietly reconciled: it is a house rule
applied to a borrowed framework, and the reader should know which is which.

The anti-imposter filter is his too, and it is the one he had to learn twice.
"I meet with entrepreneurs today and they'll tell me their strategy is to be
like Amazon, by which they mean they're going to ignore profitability. I'll
reply, 'That's interesting because that's not the Amazon story.'" Amazon's US
retail business ran at a consistent 5–7% EBIT margin before Bezos funded AWS
out of it. And after rates reset in 2022 — when 120 stocks had cleared the 20%
bar in a decade instead of 40, and "there were imposters in his portfolio" —
the re-underwriting turned on exactly that. So a positive operating margin is a
hard filter here, not a scored preference.

**And the window is nothing like his.** His compounder is a ten-year fact. This
provider returns four or five annual columns for a small cap, so the growth
rate here is a three- or four-year CAGR, and every row reports how many years
it actually had (`years_of_annual_data`) and how far short of his decade that
leaves it (`window_shortfall_years`). A three-year run rate is a weaker claim
than a ten-year record and the row has to say which one it is making.

Data via yfinance. Verify against filings before acting on any of it.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd
import yfinance as yf

from hedge_fund.screeners import principles
from hedge_fund.screeners.acquisition_compounder import (
    _cagr_5y,
    _effective_tax_rate,
    _find_income_row,
    _geom_annual_growth_over_span,
    _invested_capital_series,
    _reinvestment_rate,
    _roiic,
    _sorted_annual_values,
    _yoy_latest,
)
from hedge_fund.screeners.bolton_contrarian import _band, _ratio
from hedge_fund.screeners.yartseva import _f, _sum_q

logger = logging.getLogger(__name__)

# --- His bar, and the bar this screen actually applies -------------------
#
# The 20% decade is the definition of a compounder, not an entry test. A screen
# that demanded ten years at 20% would return the answer after the fact, which
# is the one form of this list that is worthless. So the bar held here is "on
# that path and still on it", and the distance to 20% is what the score reads.

#: The compounder definition itself. Carried as a constant because the score is
#: graded against it rather than against an invented threshold.
COMPOUNDER_CAGR = 0.20

#: The window his study measures over. Reported, not required — almost no
#: small cap has ten clean years of annual statements in this provider.
COMPOUNDER_WINDOW_YEARS = 10

#: Hard filter. Below this a company is not on a 20% path by any reading.
MIN_REV_CAGR = 0.12

#: And it has to still be growing now, not have grown. A decelerating business
#: with a flattering five-year CAGR is the commonest way this screen could lie.
MIN_REV_YOY = 0.08

# --- Act 1 proven: the Amazon test --------------------------------------
#
# "That's not the Amazon story." Unit economics that work is the third leg of
# his Act 1 definition, and the only one a feed can see.

#: Hard filter: a profitable core. This is the imposter filter, and it is the
#: single most load-bearing line in the module. The average loss-making
#: company in the Russell 2000 Growth fell over 70% when money stopped being
#: free, and his own re-underwriting in 2022 turned on this exact distinction.
MIN_EBIT_MARGIN = 0.0

#: Full marks. The top of the 5–7% band Amazon's US retail business held while
#: it funded AWS out of the cash flow.
PROVEN_EBIT_MARGIN = 0.07

#: A floor on gross margin, where the provider reports one. Low on purpose:
#: O'Reilly, Vail and RBC Bearings are his own examples, and a services
#: compounder like FirstService books labour in cost of revenue. A company with
#: no gross-profit line is not failed on it — unmeasured is not unqualified.
MIN_GROSS_MARGIN = 0.20
PREF_GROSS_MARGIN = 0.55

# --- Increasing returns on invested capital ------------------------------

#: Hard filter on the level. Deliberately below the compounder screen's 12%:
#: the test here is the slope, and an 11% return that was 4% three years ago
#: is more interesting to this framework than a flat 30%.
MIN_ROIC = 0.10
PREF_ROIC = 0.25

#: Full marks on the slope: return on capital up ten points over the window.
#: Negative is the "worst" end rather than zero, because holding returns flat
#: while trebling the business is a real achievement and should not score nil.
ROIC_SLOPE_BEST_PP = 10.0
ROIC_SLOPE_WORST_PP = -2.0

#: The business has to have got *bigger* for "better as it got bigger" to mean
#: anything. Below this much revenue growth across the window the slope is
#: reported and scored neutral rather than counted — margin recovery on a flat
#: business is a different and much commoner story.
MIN_REV_GROWTH_TO_JUDGE_SLOPE = 0.20

#: And the denominator has to exist. A company that has bought back most of
#: its equity has an invested-capital base near zero, and NOPAT over near zero
#: is not a return on capital — Medpace prints 530% on this definition, which
#: the level leg would reward with full marks for having financed the capital
#: away. Below this much invested capital per unit of revenue the level is
#: reported and scored neutral, the same treatment the slope gets. It is not a
#: failure: the business really does earn a lot on almost nothing. It is simply
#: not a number this screen can rank against a 20% return.
MIN_IC_TO_REVENUE_TO_JUDGE_ROIC = 0.10

#: And it must not be an artefact of a shrinking denominator. Buybacks reduce
#: equity, equity is in invested capital, so a company retiring stock shows a
#: mechanically rising ROIC with no operating improvement at all. When the
#: capital base fell by more than this, the slope is not treated as measured.
MAX_IC_SHRINK_TO_JUDGE_SLOPE = 0.05

# --- Reinvestment runway -------------------------------------------------
#: "Could reinvest profits at persistently high rates of return." The product
#: of the reinvestment rate and the return on *incremental* capital, which is
#: what the business compounds at unaided. Same bands as the compounder screen,
#: because it is the same quantity measured the same way.
REINVEST_SCORE_LO = 0.03
REINVEST_SCORE_HI = 0.18

# --- Owner alignment ----------------------------------------------------
#: Looser than the compounder screen's 2%, and still a real ceiling. See the
#: module note on where this desk overrules him.
MAX_SHARE_CAGR = 0.04
PREF_SHARE_CAGR = 0.0

#: Years of annual accounts to read the share count across.
SHARE_HISTORY_YEARS = 5

#: The most this screen can say about owner mentality: insiders hold a lot, or
#: they do not. Whether any of them is a founder on their second act is not in
#: the feed, and that is the thing he actually selects on.
PREF_INSIDER_STAKE = 0.15

# --- Size: the shelf where compounders begin -----------------------------
#: His study starts compounders at $1–6bn and finds about 80% of them begin as
#: small caps. The floor is his; the ceiling is this desk's $20bn, because the
#: two-thirds of his book that was already in Act 2 lived above the entry band
#: and is still worth screening for.
#:
#: Applied in the currency the company reports in rather than converted at a
#: rate invented here — the same refusal as the compounder and Kiyohara
#: screens, for the same reason: a wrong floor is invisible and either empties
#: the screen or waves everything through.
CAP_BAND_BY_CURRENCY: dict[str, tuple[float, float]] = {
    "USD": (1_000_000_000, 20_000_000_000),
    "CAD": (1_400_000_000, 28_000_000_000),
    "AUD": (1_500_000_000, 30_000_000_000),
    "GBP": (800_000_000, 16_000_000_000),
    "EUR": (900_000_000, 18_000_000_000),
    "JPY": (150_000_000_000, 3_000_000_000_000),
    "HKD": (8_000_000_000, 155_000_000_000),
    "SEK": (10_000_000_000, 200_000_000_000),
    "DKK": (7_000_000_000, 140_000_000_000),
    "NOK": (10_000_000_000, 200_000_000_000),
    "CHF": (800_000_000, 16_000_000_000),
}

# --- The transition marker: reported, never scored -----------------------
#: Down this far from the five-year high and still financially intact is the
#: setup his framework is about. Flagged, not rewarded — see the module note.
TRANSITION_DRAWDOWN = 0.40

#: His own figure. "Over the ten years they compounded at 20%, in one of those
#: years they fell 62%."
STRUCTURAL_DRAWDOWN = 0.62

#: How far back the high is taken from. Five years, monthly closes: long enough
#: to contain a transition, cheap enough to fetch for a whole universe.
DRAWDOWN_LOOKBACK = "5y"

#: What this screen cannot check, named so the result can carry it and a test
#: can assert it still does. These are not gaps to be closed later with a
#: proxy; they are the judgments the framework is made of.
UNCHECKABLE_BY_DESIGN: tuple[str, ...] = (
    "act2",
    "founder_act2",
    "transition_vs_failure",
)


@dataclass
class EllenbogenSnapshot:
    ticker: str
    name: str | None = None
    currency: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    price_current: float | None = None

    #: Annual series, oldest → newest. The slope tests need the shape, not a
    #: single figure, which is why these are carried whole.
    revenue_annual: list[float] = field(default_factory=list)
    ebit_annual: list[float] = field(default_factory=list)
    gross_profit_annual: list[float] = field(default_factory=list)
    invested_capital_annual: list[float] = field(default_factory=list)

    revenue_ttm: float | None = None
    ebit_ttm: float | None = None
    gross_profit_ttm: float | None = None
    free_cash_flow_ttm: float | None = None
    net_income_ttm: float | None = None
    tax_rate: float | None = None

    reinvestment_rate: float | None = None
    shares_latest: float | None = None
    shares_oldest: float | None = None
    share_history_years: int = 0
    held_percent_insiders: float | None = None

    price_high_5y: float | None = None
    error: str | None = None


def fetch_ellenbogen_snapshot(ticker: str) -> EllenbogenSnapshot:
    t = yf.Ticker(ticker.strip().upper())
    snap = EllenbogenSnapshot(ticker=ticker.strip().upper())
    try:
        info = t.info or {}
        if not info or (
            info.get("regularMarketPrice") is None and info.get("currentPrice") is None
        ):
            snap.error = "no_quote_or_info"
            return snap

        snap.name = info.get("shortName") or info.get("longName")
        snap.currency = (
            info.get("financialCurrency") or info.get("currency") or ""
        ).upper() or None
        snap.sector = info.get("sector")
        snap.industry = info.get("industry")
        snap.market_cap = _f(info.get("marketCap"))
        snap.price_current = _f(info.get("currentPrice") or info.get("regularMarketPrice"))
        snap.held_percent_insiders = _f(info.get("heldPercentInsiders"))

        inc_a = t.income_stmt
        bs_a = t.balance_sheet
        cf_a = t.cashflow

        rev_row = _find_income_row(inc_a, "Total Revenue", "Operating Revenue")
        if rev_row:
            snap.revenue_annual = _sorted_annual_values(inc_a, rev_row)
        ebit_row = _find_income_row(inc_a, "EBIT", "Operating Income")
        if ebit_row:
            snap.ebit_annual = _sorted_annual_values(inc_a, ebit_row)
        gp_row = _find_income_row(inc_a, "Gross Profit")
        if gp_row:
            snap.gross_profit_annual = _sorted_annual_values(inc_a, gp_row)
        snap.invested_capital_annual = _invested_capital_series(bs_a)

        q_inc = t.quarterly_income_stmt
        q_cf = t.quarterly_cashflow
        snap.revenue_ttm = _sum_q(q_inc, "Total Revenue", 0, 4)
        snap.ebit_ttm = _sum_q(q_inc, "EBIT", 0, 4) or _sum_q(q_inc, "Operating Income", 0, 4)
        snap.gross_profit_ttm = _sum_q(q_inc, "Gross Profit", 0, 4)
        snap.free_cash_flow_ttm = _sum_q(q_cf, "Free Cash Flow", 0, 4)
        snap.net_income_ttm = _sum_q(q_inc, "Net Income", 0, 4)
        snap.tax_rate = _f(info.get("effectiveTaxRate"))

        snap.reinvestment_rate = _reinvestment_rate(cf_a)
        snap.shares_latest, snap.shares_oldest, snap.share_history_years = _share_history(bs_a)
        snap.price_high_5y = _five_year_high(t)

        return snap
    except Exception as exc:  # noqa: BLE001
        snap.error = str(exc)
        return snap


def _share_history(bs_a: pd.DataFrame | None) -> tuple[float | None, float | None, int]:
    """Share count now and as far back as the annual accounts go, oldest last.

    Read off the balance sheet rather than from the cash-flow issuance line,
    because the count is the thing that dilutes the holder and the issuance
    line is frequently absent. A falling count is a buyback and reads as a
    positive here, which is the behaviour he describes in an owner-operator.
    """
    if bs_a is None or bs_a.empty or "Ordinary Shares Number" not in bs_a.index:
        return None, None, 0
    values = _sorted_annual_values(bs_a, "Ordinary Shares Number")[-SHARE_HISTORY_YEARS:]
    if not values:
        return None, None, 0
    if len(values) < 2:
        return values[-1], None, 1
    return values[-1], values[0], len(values)


def _five_year_high(t: yf.Ticker) -> float | None:
    """The highest monthly close in five years.

    Monthly rather than daily on purpose: the drawdown is a regime fact, not a
    trading level, and a daily series for a whole universe is a fetch nobody
    needs. It understates the true peak slightly, which makes the drawdown
    flag conservative — the right direction for a flag that invites work.
    """
    try:
        hist = t.history(period=DRAWDOWN_LOOKBACK, interval="1mo")
    except Exception as exc:  # noqa: BLE001
        logger.debug("no price history: %s", exc)
        return None
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    close = hist["Close"].dropna()
    if close.empty:
        return None
    return float(close.max())


@dataclass
class EllenbogenResult:
    ticker: str
    name: str | None = None
    passed: bool = False
    composite: float | None = None
    tier: str | None = None
    failures: list[str] = field(default_factory=list)

    returns_on_capital_score: float = 0.0
    act1_score: float = 0.0
    reinvestment_score: float = 0.0
    alignment_score: float = 0.0
    pricing_power_score: float = 0.0

    # --- Act 1, as far as a feed can see it ---
    #: How many annual columns the provider actually returned, and how far
    #: short of his ten-year window that leaves the measurement. A three-year
    #: run rate and a ten-year record are different claims.
    window_shortfall_years: int | None = None
    revenue_cagr: float | None = None
    revenue_yoy: float | None = None
    #: How far short of his 20% decade the growth currently runs, in points.
    #: Negative means ahead of it.
    gap_to_compounder_bar_pp: float | None = None
    ebit_margin: float | None = None
    gross_margin: float | None = None
    gross_margin_change_pp: float | None = None
    fcf_margin: float | None = None

    # --- Increasing returns on invested capital: the signature trait ---
    roic: float | None = None
    roic_oldest: float | None = None
    roic_change_pp: float | None = None
    #: False when the slope would be an artefact rather than a measurement:
    #: the business did not get bigger, or the capital base shrank under it.
    #: Scored neutral in that case, never as a failure.
    roic_slope_measured: bool = False
    roic_slope_unmeasured_reason: str | None = None
    #: False when the capital base has been financed away and the ratio is a
    #: denominator artefact rather than a return. See
    #: MIN_IC_TO_REVENUE_TO_JUDGE_ROIC.
    roic_level_measured: bool = True
    roic_level_unmeasured_reason: str | None = None
    invested_capital_to_revenue: float | None = None
    revenue_growth_over_window: float | None = None
    invested_capital_change: float | None = None
    years_of_annual_data: int = 0

    roiic: float | None = None
    reinvestment_rate: float | None = None
    implied_compounding: float | None = None

    share_cagr: float | None = None
    held_percent_insiders: float | None = None

    # --- The transition marker. Reported, never scored. ---
    drawdown_from_5y_high: float | None = None
    #: Financially intact and down past TRANSITION_DRAWDOWN. The point at
    #: which his question — failing, or transitioning? — has to be asked by a
    #: person. Not a buy signal and not part of the score.
    transition_candidate: bool = False
    #: Down past the 62% his own study found in the compounders' worst year.
    at_structural_drawdown: bool = False

    #: Always False. Whether there is a second act is a judgment about a
    #: product that does not exist yet and a market nobody has entered.
    act2_checked: bool = False
    #: Always False. He preferentially backs founders who have already built a
    #: scaled business; no feed carries who the insiders are, let alone what
    #: they built before.
    founder_act2_checked: bool = False
    unchecked: list[str] = field(default_factory=lambda: list(UNCHECKABLE_BY_DESIGN))

    snapshot: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def cap_band(currency: str | None) -> tuple[float, float] | None:
    if not currency:
        return None
    return CAP_BAND_BY_CURRENCY.get(currency.upper())


def _roic_series(
    ebit_annual: list[float], ic_annual: list[float], tax_rate: float | None
) -> list[float]:
    """NOPAT over invested capital, per annual year, oldest → newest.

    Both legs are aligned from the newest end: the statements come back with
    different numbers of columns often enough that zipping from the oldest
    would silently compare one year's profit against another year's capital.
    """
    n = min(len(ebit_annual), len(ic_annual))
    if n < 1:
        return []
    ebit, ic = ebit_annual[-n:], ic_annual[-n:]
    tr = _effective_tax_rate(tax_rate)
    out: list[float] = []
    for i in range(n):
        if ic[i] is None or ic[i] <= 0:
            continue
        out.append(ebit[i] * (1 - tr) / ic[i])
    return out


def _change(new: float | None, old: float | None) -> float | None:
    """Proportional change, or None when the base cannot carry one."""
    if new is None or old is None or old <= 0:
        return None
    return (new - old) / old


def score_ellenbogen_two_act(snap: EllenbogenSnapshot) -> EllenbogenResult:
    r = EllenbogenResult(ticker=snap.ticker, name=snap.name)
    if snap.error:
        r.error = snap.error
        return r

    r.snapshot = {k: v for k, v in asdict(snap).items() if k not in {"ticker", "error"}}

    rev = snap.revenue_annual
    r.years_of_annual_data = len(rev)
    r.window_shortfall_years = max(0, COMPOUNDER_WINDOW_YEARS - r.years_of_annual_data)

    # ---- Act 1: growth, and whether it is still happening ----
    r.revenue_cagr = _cagr_5y(rev)
    if r.revenue_cagr is None:
        r.revenue_cagr = _geom_annual_growth_over_span(rev)
    r.revenue_yoy = _yoy_latest(rev)
    if r.revenue_cagr is not None:
        r.gap_to_compounder_bar_pp = (COMPOUNDER_CAGR - r.revenue_cagr) * 100

    r.ebit_margin = _ratio(snap.ebit_ttm, snap.revenue_ttm)
    r.gross_margin = _ratio(snap.gross_profit_ttm, snap.revenue_ttm)
    r.fcf_margin = _ratio(snap.free_cash_flow_ttm, snap.revenue_ttm)

    # Gross-margin trend as the only visible trace of pricing power. "Raise
    # prices without losing customers" shows up as a margin that holds or
    # widens while revenue grows; it is a weak proxy and labelled as one.
    gp, n_gp = (
        snap.gross_profit_annual,
        min(len(snap.gross_profit_annual), len(snap.revenue_annual)),
    )
    if n_gp >= 2:
        gp, rv = gp[-n_gp:], rev[-n_gp:]
        first = _ratio(gp[0], rv[0])
        last = _ratio(gp[-1], rv[-1])
        if first is not None and last is not None:
            r.gross_margin_change_pp = (last - first) * 100
            if r.gross_margin is None:
                r.gross_margin = last

    # ---- Increasing returns on invested capital ----
    roics = _roic_series(snap.ebit_annual, snap.invested_capital_annual, snap.tax_rate)
    if roics:
        r.roic = roics[-1]
        r.roic_oldest = roics[0]
        if len(roics) >= 2:
            r.roic_change_pp = (roics[-1] - roics[0]) * 100
    if r.roic is None:
        # No usable annual pair. Fall back to the TTM level so the hard filter
        # on the *level* can still run; the slope stays unmeasured.
        nopat = (
            snap.ebit_ttm * (1 - _effective_tax_rate(snap.tax_rate))
            if snap.ebit_ttm is not None
            else None
        )
        ic_latest = snap.invested_capital_annual[-1] if snap.invested_capital_annual else None
        r.roic = _ratio(nopat, ic_latest)

    # Measured over the same number of years the slope was measured over, not
    # over whatever the revenue statement happens to carry. A five-year
    # revenue window judging a two-year ROIC slope would call a business
    # "bigger" on growth the slope never saw, which is the one way the
    # signature test could flatter a company by accident.
    ic = snap.invested_capital_annual
    window = len(roics) if len(roics) >= 2 else 0
    if window >= 2 and len(rev) >= window:
        r.revenue_growth_over_window = _change(rev[-1], rev[-window])
    if window >= 2 and len(ic) >= window:
        r.invested_capital_change = _change(ic[-1], ic[-window])

    # Is there enough capital left for "return on capital" to mean anything?
    if ic and rev and rev[-1] > 0:
        r.invested_capital_to_revenue = ic[-1] / rev[-1]
        if r.invested_capital_to_revenue < MIN_IC_TO_REVENUE_TO_JUDGE_ROIC:
            r.roic_level_measured = False
            r.roic_level_unmeasured_reason = "capital_base_financed_away"

    # Whether the slope means what it appears to mean. Two ways it does not,
    # and both are common enough that treating the number at face value would
    # make this screen's signature test its least reliable one.
    if r.roic_change_pp is None:
        r.roic_slope_unmeasured_reason = "fewer_than_two_annual_years"
    elif (
        r.revenue_growth_over_window is None
        or r.revenue_growth_over_window < MIN_REV_GROWTH_TO_JUDGE_SLOPE
    ):
        # "Better as it got bigger" needs the bigger. Margin recovery on a
        # flat business is a different story and a much commoner one.
        r.roic_slope_unmeasured_reason = "business_did_not_get_bigger"
    elif (
        r.invested_capital_change is not None
        and r.invested_capital_change < -MAX_IC_SHRINK_TO_JUDGE_SLOPE
    ):
        # Buybacks retire equity, equity sits in invested capital, so a
        # company shrinking its capital base shows a rising ROIC with no
        # operating improvement at all.
        r.roic_slope_unmeasured_reason = "capital_base_shrank"
    else:
        r.roic_slope_measured = True

    r.roiic = _roiic(snap.ebit_annual, snap.invested_capital_annual, snap.tax_rate)
    r.reinvestment_rate = snap.reinvestment_rate
    if r.roiic is not None and r.reinvestment_rate is not None:
        r.implied_compounding = r.roiic * r.reinvestment_rate

    # ---- Owner alignment ----
    if (
        snap.shares_latest
        and snap.shares_oldest
        and snap.shares_oldest > 0
        and snap.share_history_years >= 2
    ):
        years = snap.share_history_years - 1
        r.share_cagr = (snap.shares_latest / snap.shares_oldest) ** (1 / years) - 1
    r.held_percent_insiders = snap.held_percent_insiders

    # ---- The transition marker ----
    if snap.price_high_5y and snap.price_high_5y > 0 and snap.price_current is not None:
        r.drawdown_from_5y_high = max(
            0.0, (snap.price_high_5y - snap.price_current) / snap.price_high_5y
        )
        r.at_structural_drawdown = r.drawdown_from_5y_high >= STRUCTURAL_DRAWDOWN

    # ---- Hard filters ----
    fails: list[str] = []

    # Standing desk exclusions first, before anything is weighed, and named so
    # the row can say which principle removed the company rather than leaving
    # "excluded" indistinguishable from "failed on the arithmetic".
    excl = principles.excluded_by(snap.sector, snap.industry)
    if excl:
        fails.append(f"excluded_{excl.replace('-', '_')}")

    band = cap_band(snap.currency)
    if band is None:
        fails.append("cap_band_unknown_currency")
    elif snap.market_cap is None:
        fails.append("no_market_cap")
    elif snap.market_cap < band[0]:
        fails.append("below_cap_floor")
    elif snap.market_cap > band[1]:
        fails.append("above_cap_ceiling")

    if r.revenue_cagr is None:
        fails.append("no_revenue_history")
    elif r.revenue_cagr < MIN_REV_CAGR:
        fails.append("revenue_cagr_below_floor")

    if r.revenue_yoy is None:
        fails.append("no_revenue_yoy")
    elif r.revenue_yoy < MIN_REV_YOY:
        # Grew, then stopped. The flattering five-year CAGR is exactly how
        # this screen would otherwise mislead.
        fails.append("growth_has_stalled")

    if r.ebit_margin is None:
        fails.append("no_operating_margin")
    elif r.ebit_margin <= MIN_EBIT_MARGIN:
        # The imposter filter. See the module note: "that's not the Amazon story".
        fails.append("core_not_profitable")

    if r.roic is None:
        fails.append("no_return_on_capital")
    elif not r.roic_level_measured:
        # Not failed and not credited. The ratio is unrankable rather than
        # low, and refusing the company for it would be the opposite error.
        pass
    elif r.roic < MIN_ROIC:
        fails.append("roic_below_floor")

    # Unmeasured gross margin is not a failure. Services compounders report
    # labour in cost of revenue and some filers omit the line entirely.
    if r.gross_margin is not None and r.gross_margin < MIN_GROSS_MARGIN:
        fails.append("gross_margin_below_floor")

    if r.share_cagr is not None and r.share_cagr > MAX_SHARE_CAGR:
        fails.append("dilutes_the_holder")

    r.failures = fails
    r.passed = not fails

    # A transition candidate has to be intact first. Flagging a company that
    # failed the filters as "down 50%, ask the question" would be a cheapness
    # screen wearing this one's name, which is the specific mistake the module
    # note refuses.
    r.transition_candidate = (
        r.passed
        and r.drawdown_from_5y_high is not None
        and r.drawdown_from_5y_high >= TRANSITION_DRAWDOWN
    )

    # ---- Score, computed for every name that returned data ----
    #
    # Returns on capital, 30. The signature trait, and weighted as such: 18 for
    # the level and 12 for the slope, because a 30% return that has been 30%
    # forever is a good business and a 16% return that was 6% is the thing his
    # study actually found.
    level = (
        _band(r.roic, PREF_ROIC, MIN_ROIC, 18.0)
        if r.roic_level_measured
        else 9.0  # unrankable, same convention as the slope below
    )
    if r.roic_slope_measured:
        slope = _band(r.roic_change_pp, ROIC_SLOPE_BEST_PP, ROIC_SLOPE_WORST_PP, 12.0)
    else:
        # Neutral, not nil. The same convention the compounder screen uses for
        # an unmeasurable ROIIC: a 6 here means "not measured", and the reason
        # is on the row.
        slope = 6.0
    r.returns_on_capital_score = round(level + slope, 2)

    # Act 1, 25. Growth against his 20% bar, growth now, and a core that
    # actually earns money at the scale it has reached.
    act1 = _band(r.revenue_cagr, COMPOUNDER_CAGR, MIN_REV_CAGR, 12.0)
    act1 += _band(r.revenue_yoy, COMPOUNDER_CAGR, MIN_REV_YOY, 6.0)
    act1 += _band(r.ebit_margin, PROVEN_EBIT_MARGIN, MIN_EBIT_MARGIN, 7.0)
    r.act1_score = round(min(25.0, act1), 2)

    # Reinvestment runway, 20. "Could reinvest profits at persistently high
    # rates of return" is the half of the compounder definition that decides
    # whether the returns can continue, rather than describing what they were.
    if r.implied_compounding is None:
        r.reinvestment_score = 10.0  # unmeasured, same convention as the slope
    else:
        r.reinvestment_score = round(
            _band(r.implied_compounding, REINVEST_SCORE_HI, REINVEST_SCORE_LO, 20.0), 2
        )

    # Owner alignment, 15. A share count that does not grow, and insiders with
    # something to lose. Both are proxies for the thing he selects on and
    # neither is the thing itself — see `founder_act2_checked`.
    align = (
        _band(r.share_cagr, PREF_SHARE_CAGR, MAX_SHARE_CAGR, 10.0)
        if r.share_cagr is not None
        else 5.0
    )
    align += _band(r.held_percent_insiders, PREF_INSIDER_STAKE, 0.0, 5.0)
    r.alignment_score = round(min(15.0, align), 2)

    # Pricing power, 10. The level says what kind of business it is; the trend
    # is the only trace of "raise prices without losing customers" a statement
    # carries. Weighted towards the trend for that reason.
    pricing = _band(r.gross_margin, PREF_GROSS_MARGIN, MIN_GROSS_MARGIN, 4.0)
    pricing += _band(r.gross_margin_change_pp, 5.0, -5.0, 6.0)
    r.pricing_power_score = round(min(10.0, pricing), 2)

    r.composite = round(
        r.returns_on_capital_score
        + r.act1_score
        + r.reinvestment_score
        + r.alignment_score
        + r.pricing_power_score,
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


def run_ellenbogen_two_act_for_ticker(ticker: str) -> dict[str, Any]:
    snap = fetch_ellenbogen_snapshot(ticker)
    return score_ellenbogen_two_act(snap).to_dict()
