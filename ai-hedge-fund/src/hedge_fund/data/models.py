"""Pydantic models for all data categories."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# ESG
# ------------------------------------------------------------------


class ESGScores(BaseModel):
    ticker: str
    total_score: float | None = None
    environment_score: float | None = None
    social_score: float | None = None
    governance_score: float | None = None
    controversy_level: int | None = None
    peer_group: str | None = None
    source: str = "unknown"


# ------------------------------------------------------------------
# Insider transactions
# ------------------------------------------------------------------


class InsiderTransaction(BaseModel):
    ticker: str
    name: str
    title: str | None = None
    transaction_type: str  # "Buy", "Sell", "Option Exercise"
    shares: int
    value: float | None = None
    date: Optional[date] = None
    source: str = "unknown"


# ------------------------------------------------------------------
# Institutional holders
# ------------------------------------------------------------------


class InstitutionalHolder(BaseModel):
    ticker: str
    holder: str
    shares: int
    value: float | None = None
    pct_held: float | None = None
    date_reported: Optional[date] = None
    source: str = "unknown"


# ------------------------------------------------------------------
# Earnings
# ------------------------------------------------------------------


class EarningsInfo(BaseModel):
    ticker: str
    next_earnings_date: Optional[date] = None
    earnings_dates: list[dict] = Field(default_factory=list)
    quarterly_earnings: list[dict] = Field(default_factory=list)
    revenue_estimates: dict | None = None
    eps_trend: list[dict] = Field(default_factory=list)
    source: str = "unknown"


# ------------------------------------------------------------------
# Analyst ratings
# ------------------------------------------------------------------


class AnalystRating(BaseModel):
    ticker: str
    target_mean: float | None = None
    target_median: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    current_price: float | None = None
    upside_pct: float | None = None
    num_analysts: int | None = None
    recommendation: str | None = None  # "Buy", "Hold", "Sell"
    recommendation_history: list[dict] = Field(default_factory=list)
    source: str = "unknown"


# ------------------------------------------------------------------
# News + Sentiment
# ------------------------------------------------------------------


class NewsSentiment(BaseModel):
    ticker: str
    buzz_score: float | None = None
    sentiment_score: float | None = None  # -1 to 1
    articles_in_week: int | None = None
    positive_pct: float | None = None
    negative_pct: float | None = None
    sector_avg_sentiment: float | None = None
    articles: list[dict] = Field(default_factory=list)
    source: str = "unknown"


# ------------------------------------------------------------------
# Sector performance
# ------------------------------------------------------------------


class SectorChange(BaseModel):
    """One sector's move over one period."""

    sector: str
    change_pct: float


class SectorPerformance(BaseModel):
    """Sector moves, one ranked list per period.

    A list of rows rather than a `{sector: pct}` mapping, because the order is
    the information — Alpha Vantage returns these ranked best-to-worst and the
    panel reads as a ranking. A dict threw that away, and the field was named
    `real_time` while every producer and consumer said `realtime`, so nothing
    ever populated: pydantic silently dropped the unknown key and rejected the
    row lists as non-dicts, and the whole object came back as None. The wire
    shape here is the one the API fallback and the frontend type already use.
    """

    realtime: list[SectorChange] = Field(default_factory=list)
    one_day: list[SectorChange] = Field(default_factory=list)
    five_day: list[SectorChange] = Field(default_factory=list)
    one_month: list[SectorChange] = Field(default_factory=list)
    three_month: list[SectorChange] = Field(default_factory=list)
    ytd: list[SectorChange] = Field(default_factory=list)
    one_year: list[SectorChange] = Field(default_factory=list)
    source: str = "unknown"


# ------------------------------------------------------------------
# Fama-French factors
# ------------------------------------------------------------------


class FamaFrenchFactors(BaseModel):
    period: str = "monthly"
    factors: list[dict] = Field(default_factory=list)  # [{date, Mkt-RF, SMB, HML, RMW, CMA, RF}]
    description: str = "Fama-French 5-Factor Model"
    source: str = "pandas-datareader"


# ------------------------------------------------------------------
# Options
# ------------------------------------------------------------------


class OptionsChain(BaseModel):
    ticker: str
    expirations: list[str] = Field(default_factory=list)
    calls: list[dict] = Field(default_factory=list)
    puts: list[dict] = Field(default_factory=list)
    iv_rank: float | None = None
    source: str = "unknown"


# ------------------------------------------------------------------
# SEC Filings
# ------------------------------------------------------------------


class SECFiling(BaseModel):
    ticker: str
    form_type: str  # "10-K", "10-Q", "8-K", "13F"
    filed_date: Optional[date] = None
    accepted_date: Optional[datetime] = None
    report_url: str | None = None
    description: str | None = None
    source: str = "unknown"


# ------------------------------------------------------------------
# Congressional trades
# ------------------------------------------------------------------


class CongressionalTrade(BaseModel):
    ticker: str
    representative: str
    transaction_type: str  # "Purchase", "Sale"
    amount_range: str | None = None  # "$1,001 - $15,000"
    transaction_date: Optional[date] = None
    disclosure_date: Optional[date] = None
    chamber: str | None = None  # "House", "Senate"
    source: str = "unknown"


# ------------------------------------------------------------------
# Peer comparison
# ------------------------------------------------------------------


class PeerComparison(BaseModel):
    ticker: str
    peers: list[str] = Field(default_factory=list)
    sector: str | None = None
    industry: str | None = None
    metrics: dict = Field(default_factory=dict)  # {peer: {pe, market_cap, ...}}
    source: str = "unknown"
    # How the set was chosen. A comparison set is a judgment, so the response
    # says whose: "curated" for a hand-picked set, "sic" for the EDGAR
    # classification fallback, "none" when there are no peers at all. `vetted`
    # is what a screen should read before drawing a football field off it.
    basis: str = "unknown"
    vetted: bool = False
    peer_reasons: dict[str, str] = Field(default_factory=dict)
    as_of: str | None = None


# ------------------------------------------------------------------
# Provider status
# ------------------------------------------------------------------


class ProviderStatus(BaseModel):
    name: str
    available: bool
    categories: list[str]
    priority: int
    rate_limit: dict | None = None
