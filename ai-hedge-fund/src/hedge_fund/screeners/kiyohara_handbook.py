"""
Kiyohara Handbook screener — his page of the Japan Company Handbook, as code.

Tatsuro Kiyohara ran Tower K1 to roughly 93x over three decades in Japanese
small and mid caps, and then did something almost no retired manager does: he
said out loud exactly what he looked at. What he looked at was one page of the
Japan Company Handbook — the Toyo Keizai annual that is Japan's Value Line —
and a very short list of things on it:

    P/E, by business type   under 20x for a global niche leader, under 15x for
                            a company with many credible customers, under 10x
                            for a small or mid real-estate company, under 7x
                            for a subcontractor living off a few customers
    the second-year forecast the share price reflects next year, not this one,
                            so the multiple that matters is on the second year
    major shareholders      above all, how much the founder and the founder's
                            family hold
    equity ratio            enough cushion that it will not have to dilute
    net cash / market cap   how much of the price is already cash
    share issuance          has it ever had to ask the market for money
    everything else         ignored. Dividend, price chart, ratings: ignored.

Two of those cannot be read from a data feed, and this screen does not pretend
otherwise:

**Which P/E tier applies.** The tier is a judgment about the business — global
niche share, the credibility and number of its customers, whether it is a tier
two supplier dependent on one buyer. A feed carries a sector code, not a market
share. So the screen computes the second-year P/E, reports which of his four
ceilings the name is under, and records `business_type_checked: False`. The one
exception is real estate, which the sector code does give directly, so the 10x
ceiling is enforced for those names.

**Whose shares those are.** The Handbook prints the major-shareholder table
with the founder family named in it, and the trade Kiyohara described —
inheritance tax forcing a sale or a buyback when the founder dies — needs the
names and the ages. The feed gives one aggregate insider percentage, no names.
So ownership is scored as "closely held" at most, and `founder_stake_checked`
is always False.

And the omissions are deliberate, not missing work: there is no dividend field,
no momentum, no 52-week range and no analyst rating anywhere in this screen,
because he ignores all of them. A test enforces that.

Forecasts here are the analyst consensus for the next fiscal year, which is a
substitute for the Handbook's own Toyo Keizai estimate, not the same number.
Data via yfinance. Verify against filings before acting on any of it.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd
import yfinance as yf

from hedge_fund.screeners.bolton_contrarian import _band, _ratio
from hedge_fund.screeners.yartseva import _f

logger = logging.getLogger(__name__)

# --- His four P/E ceilings ----------------------------------------------
#: Business type -> the second-year P/E he would pay up to. Ordered loosest
#: first, because the screen reports every ceiling a name clears rather than
#: choosing one for it.
PE_TIERS: tuple[tuple[str, float], ...] = (
    ("global niche leader", 20.0),
    ("many credible customers", 15.0),
    ("small/mid real estate", 10.0),
    ("concentrated subcontractor", 7.0),
)

#: The loosest ceiling. Above this he is not interested whatever the business.
PE_CEILING_MAX = 20.0

#: Real estate is the one tier a sector code settles, and it was his bread and
#: butter, so it is enforced rather than merely reported.
REAL_ESTATE_PE_CEILING = 10.0
REAL_ESTATE_SECTORS = ("real estate",)

# --- Scored preferences -------------------------------------------------
#: "Enough of a cushion to avoid any kind of dilution." Below this the next
#: downturn is an equity raise, which is the thing the test exists to avoid.
MIN_EQUITY_RATIO = 0.30
PREF_EQUITY_RATIO = 0.70

#: Net cash worth a third of the market value is the Japanese small-cap
#: condition he was famous for exploiting. Full marks there.
PREF_NET_CASH_RATIO = 0.35

#: Share count growth past this over the window is "they have asked the market
#: for money" — noted, per his own wording, not disqualifying.
ISSUANCE_SHARE_GROWTH = 0.02

#: Years of annual accounts to read the share count across.
SHARE_HISTORY_YEARS = 4

#: A size floor, in the currency the company reports in, because the screen
#: runs on a Japanese universe where market caps are quoted in yen and a
#: dollar floor would admit everything. Roughly $65m at either end.
#:
#: Unlisted currencies are refused rather than converted at a rate invented
#: here: a wrong floor is invisible, and it either empties the screen or waves
#: every micro-cap through.
MIN_MARKET_CAP_BY_CURRENCY: dict[str, float] = {
    "JPY": 10_000_000_000,
    "USD": 65_000_000,
    "EUR": 60_000_000,
    "GBP": 50_000_000,
    "HKD": 500_000_000,
}

#: What he says to ignore, kept as data so the test can assert the screen
#: never grew a field for any of it.
IGNORED_BY_DESIGN = ("dividend", "price chart", "analyst rating", "momentum")


@dataclass
class KiyoharaSnapshot:
    ticker: str
    name: str | None = None
    currency: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    price_current: float | None = None
    eps_trailing: float | None = None
    #: Consensus EPS for the fiscal year in progress (the Handbook's first
    #: forecast column).
    eps_fy1: float | None = None
    #: And for the year after it — the number he actually works from.
    eps_fy2: float | None = None
    fy2_analyst_count: int | None = None
    total_assets: float | None = None
    stockholders_equity: float | None = None
    cash_and_st_investments: float | None = None
    total_debt: float | None = None
    shares_latest: float | None = None
    shares_oldest: float | None = None
    share_history_years: int = 0
    equity_issued_recently: bool = False
    held_percent_insiders: float | None = None
    error: str | None = None


def _annual(df: pd.DataFrame | None, row: str, col: int = 0) -> float | None:
    """One line of an annual statement, newest column first."""
    if df is None or df.empty or row not in df.index:
        return None
    series = df.loc[row]
    if col >= len(series):
        return None
    return _f(series.iloc[col])


def _first_annual(df: pd.DataFrame | None, rows: tuple[str, ...]) -> float | None:
    """The first of several row spellings that the provider actually returned."""
    for r in rows:
        v = _annual(df, r)
        if v is not None:
            return v
    return None


def _estimate(df: pd.DataFrame | None, period: str, column: str) -> float | None:
    if df is None or df.empty or period not in df.index:
        return None
    if column not in df.columns:
        return None
    return _f(df.loc[period, column])


def fetch_kiyohara_snapshot(ticker: str) -> KiyoharaSnapshot:
    t = yf.Ticker(ticker.strip().upper())
    snap = KiyoharaSnapshot(ticker=ticker.strip().upper())
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
        snap.eps_trailing = _f(info.get("trailingEps"))
        snap.held_percent_insiders = _f(info.get("heldPercentInsiders"))

        # The second-year forecast, which is the whole point. `forwardEps` is
        # the same figure, but only when the provider has it; the estimate
        # table carries both forecast years and the analyst count behind them,
        # and a one-analyst forecast is a different object from a twelve-
        # analyst one even when the number is identical.
        try:
            est = t.earnings_estimate
        except Exception as exc:  # noqa: BLE001
            est = None
            logger.debug("%s: no earnings estimate table (%s)", snap.ticker, exc)
        snap.eps_fy1 = _estimate(est, "0y", "avg")
        snap.eps_fy2 = _estimate(est, "+1y", "avg")
        if snap.eps_fy2 is None:
            snap.eps_fy2 = _f(info.get("forwardEps"))
        n = _estimate(est, "+1y", "numberOfAnalysts")
        snap.fy2_analyst_count = int(n) if n is not None else None

        bs = t.balance_sheet
        snap.total_assets = _annual(bs, "Total Assets")
        snap.stockholders_equity = _first_annual(
            bs, ("Stockholders Equity", "Total Equity Gross Minority Interest")
        )
        snap.cash_and_st_investments = _first_annual(
            bs,
            (
                "Cash Cash Equivalents And Short Term Investments",
                "Cash And Cash Equivalents",
            ),
        )
        snap.total_debt = _annual(bs, "Total Debt")
        if snap.total_debt is None:
            snap.total_debt = _f(info.get("totalDebt"))

        try:
            splits = t.splits
        except Exception:  # noqa: BLE001
            splits = None
        snap.shares_latest, snap.shares_oldest, snap.share_history_years = _share_history(
            bs, splits
        )
        snap.equity_issued_recently = _issued_equity(t, snap.market_cap)

        return snap
    except Exception as exc:  # noqa: BLE001
        snap.error = str(exc)
        return snap


def _share_history(
    bs: pd.DataFrame | None, splits: pd.Series | None = None
) -> tuple[float | None, float | None, int]:
    """Share count now, and as far back as the accounts go, split-adjusted.

    Counted from the balance sheet rather than from the cash-flow issuance
    line, because the issuance line is frequently absent for Japanese filers
    while the share count is not — and the count is the thing that dilutes
    you. A buyback shows up here as a fall, which Kiyohara reads as a positive.

    The split adjustment is not a nicety. Balance-sheet counts are as
    reported, so a two-for-one split — common among Japanese mid caps, and
    economically nothing — doubles the count and would be read as the company
    having issued half of itself to the market. That is the one error this
    section must not make, since "has it ever had to ask for money" is the
    question, and the answer would be wrong in the worst direction.
    """
    if bs is None or bs.empty or "Ordinary Shares Number" not in bs.index:
        return None, None, 0
    series = pd.to_numeric(bs.loc["Ordinary Shares Number"], errors="coerce").dropna()
    series = series.iloc[:SHARE_HISTORY_YEARS]
    if len(series) == 0:
        return None, None, 0
    if len(series) < 2:
        return float(series.iloc[0]), None, 1

    oldest = float(series.iloc[-1]) * _split_factor(splits, series.index[-1], series.index[0])
    return float(series.iloc[0]), oldest, len(series)


def _split_factor(splits: pd.Series | None, start: Any, end: Any) -> float:
    """How much splits alone multiplied the share count between two dates."""
    if splits is None or len(splits) == 0:
        return 1.0
    try:
        idx = pd.to_datetime(splits.index, utc=True, errors="coerce")
        lo = pd.to_datetime(start, utc=True)
        hi = pd.to_datetime(end, utc=True)
    except (TypeError, ValueError):
        return 1.0
    factor = 1.0
    for when, ratio in zip(idx, splits.to_numpy(), strict=False):
        if pd.isna(when) or when <= lo or when > hi:
            continue
        value = _f(ratio)
        if value and value > 0:
            factor *= value
    return factor


def _issued_equity(t: yf.Ticker, market_cap: float | None) -> bool:
    """Did it raise equity in the years on file, at a size worth noting?

    Scaled by market value rather than taken absolutely: every company issues
    a trickle of stock through option plans, and reading that as "went to the
    market for money" would flag the entire universe.
    """
    try:
        cf = t.cashflow
    except Exception:  # noqa: BLE001
        return False
    if cf is None or cf.empty or not market_cap or market_cap <= 0:
        return False
    for row in ("Issuance Of Capital Stock", "Common Stock Issuance"):
        if row not in cf.index:
            continue
        values = pd.to_numeric(cf.loc[row], errors="coerce").dropna()
        if any(float(v) > market_cap * 0.01 for v in values):
            return True
    return False


@dataclass
class KiyoharaResult:
    ticker: str
    name: str | None = None
    passed: bool = False
    composite: float | None = None
    tier: str | None = None
    failures: list[str] = field(default_factory=list)

    valuation_score: float = 0.0
    forecast_score: float = 0.0
    equity_ratio_score: float = 0.0
    net_cash_score: float = 0.0
    capital_discipline_score: float = 0.0
    closely_held_score: float = 0.0

    #: Price over the consensus EPS for the year after this one.
    pe_second_year: float | None = None
    pe_first_year: float | None = None
    #: Which of his four ceilings this multiple is under, loosest first.
    tiers_cleared: list[str] = field(default_factory=list)
    #: Enforced only where the sector code settles it — real estate.
    pe_ceiling_applied: float | None = None
    fy2_growth_pct: float | None = None
    fy1_vs_trailing_pct: float | None = None
    equity_ratio: float | None = None
    net_cash: float | None = None
    net_cash_ratio: float | None = None
    share_count_change_pct: float | None = None
    equity_issued_recently: bool = False
    held_percent_insiders: float | None = None

    #: Always False: which P/E tier applies is a judgment about market share
    #: and customer concentration, and no feed carries either.
    business_type_checked: bool = False
    #: Always False: the Handbook names the founder's family in the
    #: shareholder table. The feed gives one anonymous insider percentage.
    founder_stake_checked: bool = False

    snapshot: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _size_floor(currency: str | None) -> float | None:
    if not currency:
        return None
    return MIN_MARKET_CAP_BY_CURRENCY.get(currency.upper())


def _pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100


def score_kiyohara_handbook(snap: KiyoharaSnapshot) -> KiyoharaResult:
    r = KiyoharaResult(ticker=snap.ticker, name=snap.name)
    if snap.error:
        r.error = snap.error
        return r

    r.snapshot = {k: v for k, v in asdict(snap).items() if k not in {"ticker", "error"}}

    px = snap.price_current
    r.pe_first_year = _ratio(px, snap.eps_fy1) if snap.eps_fy1 and snap.eps_fy1 > 0 else None
    r.pe_second_year = _ratio(px, snap.eps_fy2) if snap.eps_fy2 and snap.eps_fy2 > 0 else None
    r.tiers_cleared = [
        label for label, ceiling in PE_TIERS if r.pe_second_year and r.pe_second_year < ceiling
    ]
    r.fy2_growth_pct = _pct_change(snap.eps_fy2, snap.eps_fy1)
    r.fy1_vs_trailing_pct = _pct_change(snap.eps_fy1, snap.eps_trailing)
    r.equity_ratio = _ratio(snap.stockholders_equity, snap.total_assets)
    if snap.cash_and_st_investments is not None:
        r.net_cash = snap.cash_and_st_investments - (snap.total_debt or 0.0)
        r.net_cash_ratio = _ratio(r.net_cash, snap.market_cap)
    r.share_count_change_pct = _pct_change(snap.shares_latest, snap.shares_oldest)
    r.equity_issued_recently = snap.equity_issued_recently
    r.held_percent_insiders = snap.held_percent_insiders

    is_real_estate = (snap.sector or "").strip().lower() in REAL_ESTATE_SECTORS
    r.pe_ceiling_applied = REAL_ESTATE_PE_CEILING if is_real_estate else PE_CEILING_MAX

    # ---- Hard filters ----
    fails: list[str] = []

    floor = _size_floor(snap.currency)
    if floor is None:
        # Refused rather than guessed. See MIN_MARKET_CAP_BY_CURRENCY.
        fails.append("size_floor_unknown_currency")
    elif snap.market_cap is None or snap.market_cap < floor:
        fails.append("market_cap_below_floor")

    if r.pe_second_year is None:
        # Not "expensive" — unknowable. His whole method runs off the
        # second-year forecast, so a name without one cannot be judged by it.
        fails.append("no_second_year_forecast")
    elif r.pe_second_year >= r.pe_ceiling_applied:
        fails.append("above_real_estate_tier" if is_real_estate else "above_every_pe_tier")

    if r.equity_ratio is None:
        fails.append("no_equity_ratio")
    elif r.equity_ratio < MIN_EQUITY_RATIO:
        fails.append("equity_ratio_below_floor")

    r.failures = fails
    r.passed = not fails

    # ---- Score, computed for every name that returned data ----
    # Valuation, 30. Against the multiple itself rather than against a tier,
    # because choosing the tier would mean asserting the business type this
    # screen is explicit about not knowing. `tiers_cleared` carries that.
    r.valuation_score = _band(r.pe_second_year, 6.0, PE_CEILING_MAX, 30.0)

    # Forecast, 20. He weights the second year because that is what the price
    # is already reflecting, so most of the weight sits on fy1 -> fy2.
    fc = _band(r.fy2_growth_pct, 20.0, -5.0, 12.0)
    fc += _band(r.fy1_vs_trailing_pct, 15.0, -10.0, 8.0)
    r.forecast_score = min(20.0, fc)

    # Equity ratio, 20. The cushion that means it will not have to dilute.
    r.equity_ratio_score = _band(r.equity_ratio, PREF_EQUITY_RATIO, MIN_EQUITY_RATIO, 20.0)

    # Net cash against market value, 15. Negative net cash scores zero rather
    # than negative: debt is already punished through the equity ratio, and
    # counting it twice would rank a leveraged compounder below a shell.
    r.net_cash_score = _band(r.net_cash_ratio, PREF_NET_CASH_RATIO, 0.0, 15.0)

    # Capital structure, 10. Has it had to ask the market for money.
    if r.equity_issued_recently:
        cap = 0.0
    elif r.share_count_change_pct is None:
        cap = 5.0  # no history either way
    else:
        # A falling count is a buyback, which he reads as a positive — and is
        # one of the two ways the inheritance-tax trade resolves.
        cap = _band(r.share_count_change_pct, -5.0, ISSUANCE_SHARE_GROWTH * 100, 10.0)
    r.capital_discipline_score = cap

    # Closely held, 5. The most this screen can honestly say about the
    # shareholder register: insiders hold a lot, or they do not. Who they are,
    # and whether a founder is 78 years old, is not in the feed.
    r.closely_held_score = _band(r.held_percent_insiders, 0.40, 0.05, 5.0)

    r.composite = round(
        r.valuation_score
        + r.forecast_score
        + r.equity_ratio_score
        + r.net_cash_score
        + r.capital_discipline_score
        + r.closely_held_score,
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


def run_kiyohara_handbook_for_ticker(ticker: str) -> dict[str, Any]:
    snap = fetch_kiyohara_snapshot(ticker)
    return score_kiyohara_handbook(snap).to_dict()
