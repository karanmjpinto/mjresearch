"""Who the AI buyers are shopping for — and the one question this cannot answer.

Three sources sit behind this screen, and the first useful thing to say is
that they do not agree, because two of them are about buying companies and the
third is not about that at all.

**OpenAI's DeployCo** is a deployment company, not a fund: backed with over
$4bn alongside TPG, Bain, Brookfield, Goldman, McKinsey and Capgemini, and
majority-owned by OpenAI. Its first acquisition was Tomoro, an AI consultancy,
for roughly 150 engineers. What a lab buys is *delivery capacity* — people who
can put a model into an enterprise, and the enterprise relationships that let
them. It is buying a route to the customer, not a cash flow.

**The AI-enabled services roll-up** — General Catalyst, Thrive Holdings and
the firms copying them — is the opposite trade. It buys ordinary, cash-
generating services businesses and compresses the labour cost with AI, using
the cash to buy the next one. Its stated preference is for *smaller* operators,
because the efficiency delta after automation is larger where the operation was
least industrialised.

**The a16z essay is not a rollup thesis and is not about acquisitions.** David
George argues that public software must pick one of two paths within 12-24
months: accelerate growth by 10+ points with genuinely new AI-native product,
or rebuild for 40%+ true operating margins including stock comp. The claim is
that the comfortable middle is over. That yields a *warning*, not a target
list, and it is carried here as `comfortable_middle` rather than as score —
a company stuck between the two paths is one to avoid owning, which is not the
same as one worth buying.

So this screen scores two different fits and refuses to average them. A name
can be an excellent rollup target and a terrible lab target, and a single
number hiding that is worse than two numbers that disagree.

WHAT IS COMPUTABLE HERE, AND WHAT IS NOT

The *shape* is computable, and it is what this measures:

  revenue per employee     low means labour is the cost base, which is the
                           thing AI compresses. High means you are buying
                           software margins that already exist.
  the margin wedge         gross margin minus operating margin is overhead
                           and delivery labour as a share of revenue. It is
                           the spread a buyer claims to close.
  asset intensity          capex over revenue. Asset-light means the price is
                           for cash flows, not for plant.
  fragmentation            how many companies in the same industry sit inside
                           the buyable band, counted in the universe actually
                           being screened. A runway is a number here rather
                           than an adjective, and it is the one measure on
                           this screen that most published screens cannot be
                           bothered to compute.
  owner-operator           insider holding, as a proxy for a seller who can
                           actually decide to sell.
  financeable              leverage and cash conversion, because a rollup is
                           bought with debt against the target's own cash.

**Whether AI actually compresses cost-to-serve in a specific business is not
computable, and this screen does not pretend otherwise.** It depends on how
documented the work is, how much of it is judgment, how customers feel about
being served by a machine, and whether the people who know how it works stay.
That is registered as a judgment in the sense `principles.py` means it: true,
material, and deliberately not scored. Every row says so, and a reader who
treats the score as the answer has misread it.

The industry allowlist is the second honest limit. It is matched on the
industry *label* a provider reports, which is coarse: a software company whose
revenue is two-thirds implementation services reads as software here, and a
services firm classified as "Specialty Business Services" covers everything
from staffing to testing labs. This removes the obviously-not-services and
nothing finer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

#: --- What counts as a services business -------------------------------
#:
#: Matched as a case-insensitive substring of the reported industry, because
#: providers spell these inconsistently ("Information Technology Services"
#: and "IT Services" are the same shelf). Deliberately broad: the cost of
#: admitting a name the reader rejects is one row to skim, and the cost of
#: excluding one is that it never appears and nobody knows it was dropped.
SERVICES_INDUSTRIES: tuple[str, ...] = (
    "information technology services",
    "it services",
    "consulting services",
    "specialty business services",
    "staffing & employment services",
    "staffing",
    "insurance brokers",
    "security & protection services",
    "engineering & construction",
    "research services",
    "advertising agencies",
    "medical care facilities",
    "health information services",
    "diagnostics & research",
    "integrated freight & logistics",
    "rental & leasing services",
    "waste management",
    "education & training services",
    "financial data & stock exchanges",
    "software - application",
    "software - infrastructure",
)

#: Industries where the a16z two-paths warning is the relevant lens, because
#: the essay is explicitly about public *software* rather than services.
SOFTWARE_INDUSTRIES: tuple[str, ...] = (
    "software - application",
    "software - infrastructure",
)

#: --- Hard filters ------------------------------------------------------
#:
#: Size band in USD-equivalent terms, in the currency the company is quoted
#: in, following `CAP_BAND_BY_CURRENCY` in the compounder — unlisted
#: currencies are refused rather than converted at an invented rate.
#:
#: The ceiling is low on purpose and is the single most opinionated number
#: here. A rollup buyer is looking for operators small enough that the
#: post-automation delta is large and the cheque is writable; above roughly
#: $8bn you are describing an acquirer, not a target. The floor keeps out
#: the shells that have an industry label and no business.
CAP_BAND_BY_CURRENCY: dict[str, tuple[float, float]] = {
    "USD": (50_000_000, 8_000_000_000),
    "CAD": (70_000_000, 11_000_000_000),
    "AUD": (75_000_000, 12_000_000_000),
    "GBP": (40_000_000, 6_400_000_000),
    "EUR": (45_000_000, 7_200_000_000),
    "JPY": (7_500_000_000, 1_200_000_000_000),
    "HKD": (400_000_000, 62_000_000_000),
    "SEK": (500_000_000, 80_000_000_000),
    "DKK": (350_000_000, 56_000_000_000),
    "NOK": (500_000_000, 80_000_000_000),
    "CHF": (40_000_000, 6_400_000_000),
    "ZAC": (900_000_000, 144_000_000_000),
    "IDR": (800_000_000_000, 128_000_000_000_000),
    "SAR": (190_000_000, 30_000_000_000),
    "MYR": (210_000_000, 34_000_000_000),
    "THB": (1_600_000_000, 256_000_000_000),
    "CLP": (47_500_000_000, 7_600_000_000_000),
    "KRW": (70_000_000_000, 11_600_000_000_000),
}

#: Capex over revenue. Above this the business is buying plant, and the
#: purchase price stops being a multiple of cash flow.
MAX_CAPEX_TO_REVENUE = 0.12

#: Leverage a buyer can refinance. Above it the target's own balance sheet
#: is already spoken for.
MAX_NET_DEBT_TO_EBITDA = 4.0

#: --- The two fits, scored separately -----------------------------------
#:
#: Revenue per employee is the axis the two buyers read in opposite
#: directions, which is why one number could not carry both.
#:
#: A rollup wants it LOW: labour is the cost base, so there is something to
#: compress. Below this a business is essentially a payroll with a brand on
#: it, which is the ideal input to the trade.
ROLLUP_REV_PER_EMPLOYEE_BEST = 120_000.0
ROLLUP_REV_PER_EMPLOYEE_WORST = 400_000.0

#: A lab wants it HIGH, and wants engineers rather than headcount: DeployCo
#: bought 150 people, not 15,000. High revenue per head in an IT services or
#: consulting shell is the signature of a delivery team that is already
#: expensive and already technical.
LAB_REV_PER_EMPLOYEE_BEST = 300_000.0
LAB_REV_PER_EMPLOYEE_WORST = 90_000.0

#: The wedge between gross and operating margin: delivery labour and
#: overhead as a share of revenue. This is the spread a buyer claims to
#: close, so a wide one is the opportunity and a narrow one means somebody
#: already closed it.
WEDGE_BEST = 0.30
WEDGE_WORST = 0.08

#: Peers in the same industry inside the band, counted in the universe being
#: screened. Fragmentation is the whole rollup thesis and this is the only
#: place it becomes a number.
FRAGMENTATION_BEST = 12
FRAGMENTATION_WORST = 2

#: An owner who can decide to sell. Not a controlling stake — a founder or
#: family holding large enough that a bid reaches one table.
INSIDER_BEST = 0.15
INSIDER_WORST = 0.01

#: Cash conversion, because a rollup is serviced out of the target's cash.
FCF_CONVERSION_BEST = 0.90
FCF_CONVERSION_WORST = 0.35

#: --- The a16z warning --------------------------------------------------
#:
#: "The comfortable middle is over": a software company that is neither
#: accelerating growth by 10+ points nor rebuilt for 40%+ true operating
#: margin. Both halves must fail for the flag to fire — this marks the
#: stuck, not the merely unexceptional.
MIDDLE_MAX_GROWTH = 0.10
MIDDLE_MAX_OPERATING_MARGIN = 0.40

#: Said on every row, scored on none of them. The same contract
#: `principles.py` uses for a judgment: recorded as unenforceable rather
#: than turned into a number that would look like the others and mean
#: nothing.
UNCHECKABLE_BY_DESIGN: tuple[str, ...] = (
    "whether the work is documented well enough for a model to learn it",
    "how much of the delivery is judgment a customer is paying a person for",
    "whether customers accept being served by a machine",
    "whether the people who know how it works stay after the sale",
    "whether the seller will actually sell, and at what multiple",
)


@dataclass
class RollupSnapshot:
    ticker: str
    name: str | None = None
    currency: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    revenue_ttm: float | None = None
    employees: int | None = None
    revenue_per_employee: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    margin_wedge: float | None = None
    capex_to_revenue: float | None = None
    net_debt_to_ebitda: float | None = None
    fcf_conversion: float | None = None
    insider_pct: float | None = None
    revenue_growth: float | None = None
    error: str | None = None


@dataclass
class RollupResult:
    ticker: str
    passed: bool = False
    failures: list[str] = field(default_factory=list)
    rollup_score: float = 0.0
    lab_score: float = 0.0
    comfortable_middle: bool = False
    peers_in_band: int | None = None
    scores: dict[str, float] = field(default_factory=dict)
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


def _band(currency: str | None) -> tuple[float, float] | None:
    if not currency:
        return None
    return CAP_BAND_BY_CURRENCY.get(currency.upper())


def is_services(industry: str | None) -> bool:
    if not industry:
        return False
    low = industry.lower()
    return any(k in low for k in SERVICES_INDUSTRIES)


def is_software(industry: str | None) -> bool:
    if not industry:
        return False
    low = industry.lower()
    return any(k in low for k in SOFTWARE_INDUSTRIES)


def _ramp(value: float | None, best: float, worst: float, points: float) -> float:
    """Linear score between two anchors, in whichever direction they imply.

    `best` may be below `worst` — that is how one measure scores in opposite
    directions for the two buyers without a second function and a boolean.
    """
    if value is None:
        return 0.0
    if best > worst:
        if value >= best:
            return points
        if value <= worst:
            return 0.0
        return points * (value - worst) / (best - worst)
    if value <= best:
        return points
    if value >= worst:
        return 0.0
    return points * (worst - value) / (worst - best)


def fetch_rollup_snapshot(ticker: str) -> RollupSnapshot:
    t = yf.Ticker(ticker.strip().upper())
    snap = RollupSnapshot(ticker=ticker.strip().upper())
    try:
        info = t.info or {}
        if not info or (
            info.get("regularMarketPrice") is None and info.get("currentPrice") is None
        ):
            snap.error = "no_quote_or_info"
            return snap

        snap.name = info.get("shortName") or info.get("longName")
        snap.currency = (
            info.get("currency") or info.get("financialCurrency") or ""
        ).upper() or None
        snap.sector = info.get("sector")
        snap.industry = info.get("industry")
        snap.market_cap = _f(info.get("marketCap"))
        snap.revenue_ttm = _f(info.get("totalRevenue"))
        snap.gross_margin = _f(info.get("grossMargins"))
        snap.operating_margin = _f(info.get("operatingMargins"))
        snap.insider_pct = _f(info.get("heldPercentInsiders"))
        snap.revenue_growth = _f(info.get("revenueGrowth"))

        emp = info.get("fullTimeEmployees")
        snap.employees = int(emp) if isinstance(emp, (int, float)) and emp and emp > 0 else None

        if snap.revenue_ttm and snap.employees:
            snap.revenue_per_employee = snap.revenue_ttm / snap.employees

        if snap.gross_margin is not None and snap.operating_margin is not None:
            snap.margin_wedge = snap.gross_margin - snap.operating_margin

        ebitda = _f(info.get("ebitda"))
        debt = _f(info.get("totalDebt")) or 0.0
        cash = _f(info.get("totalCash")) or 0.0
        if ebitda and ebitda > 0:
            snap.net_debt_to_ebitda = (debt - cash) / ebitda

        fcf = _f(info.get("freeCashflow"))
        if fcf is not None and ebitda and ebitda > 0:
            snap.fcf_conversion = fcf / ebitda

        capex = _f(info.get("capitalExpenditures"))
        if capex is None:
            cf = t.cashflow
            if cf is not None and not cf.empty:
                for key in ("Capital Expenditure", "Capital Expenditures"):
                    if key in cf.index:
                        capex = (
                            _f(cf.loc[key].dropna().iloc[0])
                            if not cf.loc[key].dropna().empty
                            else None
                        )
                        break
        if capex is not None and snap.revenue_ttm:
            snap.capex_to_revenue = abs(capex) / snap.revenue_ttm

    except Exception as exc:  # noqa: BLE001 — one bad name must not stop a run
        logger.debug("rollup snapshot for %s failed: %s", ticker, exc)
        snap.error = f"fetch_failed: {type(exc).__name__}"
    return snap


def evaluate(snap: RollupSnapshot, peers_in_band: int | None = None) -> RollupResult:
    """Score one name against both buyers. `peers_in_band` comes from the run."""
    r = RollupResult(ticker=snap.ticker, peers_in_band=peers_in_band)
    r.snapshot = {k: v for k, v in snap.__dict__.items() if k != "error"}

    if snap.error:
        r.error = snap.error
        r.failures.append("fetch_error")
        return r

    fails = r.failures
    if not is_services(snap.industry):
        fails.append("not_a_services_industry")

    band = _band(snap.currency)
    if snap.market_cap is None:
        fails.append("missing_market_cap")
    elif band is None:
        fails.append("cap_band_unknown_currency")
    elif snap.market_cap < band[0]:
        fails.append("market_cap_below_floor")
    elif snap.market_cap > band[1]:
        fails.append("market_cap_above_ceiling")

    # Without headcount there is no labour intensity, and labour intensity is
    # the whole screen. Refused rather than scored as zero, which would read
    # as a business with no staff.
    if snap.employees is None:
        fails.append("headcount_not_reported")
    if snap.revenue_ttm is None or snap.revenue_ttm <= 0:
        fails.append("missing_revenue")
    if snap.margin_wedge is None:
        fails.append("missing_margins")
    if snap.capex_to_revenue is not None and snap.capex_to_revenue > MAX_CAPEX_TO_REVENUE:
        fails.append("too_asset_heavy")
    if snap.net_debt_to_ebitda is not None and snap.net_debt_to_ebitda > MAX_NET_DEBT_TO_EBITDA:
        fails.append("already_levered")

    r.passed = not fails

    # The a16z flag is independent of passing: it is a warning about a company
    # you might own, not a filter on one you might buy.
    if is_software(snap.industry):
        r.comfortable_middle = (
            snap.revenue_growth is not None
            and snap.revenue_growth < MIDDLE_MAX_GROWTH
            and snap.operating_margin is not None
            and snap.operating_margin < MIDDLE_MAX_OPERATING_MARGIN
        )

    if not r.passed:
        return r

    s = r.scores
    s["labour_intensity"] = _ramp(
        snap.revenue_per_employee, ROLLUP_REV_PER_EMPLOYEE_BEST, ROLLUP_REV_PER_EMPLOYEE_WORST, 10
    )
    s["margin_wedge"] = _ramp(snap.margin_wedge, WEDGE_BEST, WEDGE_WORST, 10)
    s["fragmentation"] = _ramp(
        float(peers_in_band) if peers_in_band is not None else None,
        float(FRAGMENTATION_BEST),
        float(FRAGMENTATION_WORST),
        8,
    )
    s["owner_operator"] = _ramp(snap.insider_pct, INSIDER_BEST, INSIDER_WORST, 6)
    s["cash_conversion"] = _ramp(snap.fcf_conversion, FCF_CONVERSION_BEST, FCF_CONVERSION_WORST, 8)
    s["balance_sheet"] = _ramp(snap.net_debt_to_ebitda, 0.5, MAX_NET_DEBT_TO_EBITDA, 8)
    r.rollup_score = round(sum(s.values()), 1)

    # The lab reads the same business the other way up: it wants an expensive
    # technical team and does not care about the wedge, because it is not
    # buying the margin.
    lab = _ramp(
        snap.revenue_per_employee, LAB_REV_PER_EMPLOYEE_BEST, LAB_REV_PER_EMPLOYEE_WORST, 24
    )
    if snap.industry and any(
        k in snap.industry.lower()
        for k in ("information technology services", "it services", "consulting services")
    ):
        lab += 16
    lab += _ramp(snap.revenue_growth, 0.20, 0.0, 10)
    r.lab_score = round(min(50.0, lab), 1)
    return r


def count_peers_in_band(snapshots: list[RollupSnapshot]) -> dict[str, int]:
    """How many screened names share each industry, inside the size band.

    The fragmentation measure, and the reason it is computed over the run
    rather than per name: a runway is a property of the shelf, not of the
    company standing on it. Counted only over names that are in-band and in
    a services industry, so a crowded industry of mega caps does not read as
    a fragmented one.
    """
    counts: dict[str, int] = {}
    for s in snapshots:
        band = _band(s.currency)
        if not s.industry or not is_services(s.industry) or band is None:
            continue
        if s.market_cap is None or not (band[0] <= s.market_cap <= band[1]):
            continue
        key = s.industry.strip().lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


def _row(r: RollupResult) -> dict[str, Any]:
    return {
        "ticker": r.ticker,
        "passed": r.passed,
        "failures": r.failures,
        "rollup_score": r.rollup_score,
        "lab_score": r.lab_score,
        "comfortable_middle": r.comfortable_middle,
        "peers_in_band": r.peers_in_band,
        "scores": r.scores,
        "snapshot": r.snapshot,
        "unchecked": list(r.unchecked),
        "error": r.error,
    }


def run_ai_rollup_for_ticker(ticker: str) -> dict[str, Any]:
    """One name, scored without its fragmentation component.

    Fragmentation is a property of the shelf, not of the company standing on
    it, so it cannot be known from a single ticker — the runner that the
    refresh script fans out over the universe has no idea what else is in
    that universe. The component is therefore left unscored here and filled
    in by `finalise_run` once the whole pass has landed.

    Scored as absent rather than as zero. Zero is a claim that the industry
    has no other listed operators in the band, which is the opposite of what
    "not yet counted" means, and it is the difference between a name that
    cannot be rolled up and one nobody has measured.
    """
    return _row(evaluate(fetch_rollup_snapshot(ticker), peers_in_band=None))


def finalise_run(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill in fragmentation once the whole universe has been fetched.

    The second pass the per-ticker runner cannot do. Snapshots are rebuilt
    from the rows rather than re-fetched: the data is already on disk, and
    going back to the provider for several hundred names to recount
    something already in hand would double the slowest part of the run.

    Rows that errored are passed through untouched. A name whose fetch failed
    has no industry and no market cap, so it cannot contribute to a peer
    count and must not be re-scored into looking as though it could.
    """
    snaps: list[RollupSnapshot] = []
    for row in rows:
        snap_d = row.get("snapshot")
        if row.get("error") or not isinstance(snap_d, dict):
            continue
        snaps.append(RollupSnapshot(**{k: v for k, v in snap_d.items() if k != "error"}))

    peers = count_peers_in_band(snaps)
    by_ticker = {s.ticker: s for s in snaps}

    out: list[dict[str, Any]] = []
    for row in rows:
        snap = by_ticker.get(str(row.get("ticker") or ""))
        if snap is None:
            out.append(row)
            continue
        key = (snap.industry or "").strip().lower()
        out.append(_row(evaluate(snap, peers_in_band=peers.get(key))))
    return out
