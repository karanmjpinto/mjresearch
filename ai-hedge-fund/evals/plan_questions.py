"""The questions the plan pipeline is measured on, and what answering them takes.

Bridgewater's PAT is judged on whether it does an analyst's actual work, so
this set is written the same way: thirty questions a person running this desk
would type, on the five companies already frozen in `evals/fixtures/`.

Each question carries `needs` — the capabilities a good answer cannot do
without. `CAPABILITIES` maps each one to the registered metric that provides
it, or to None where nothing does yet. Coverage is then a count rather than an
opinion: a question is covered when every capability it needs has a metric.

The tags are the one judged part of this file, and they are judged once, here,
where they can be argued with — not re-judged by a model on every run. Adding
a metric moves coverage only when it fills a tag that was None, which is the
point: the number cannot be raised by renaming things.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Capability → the metric that provides it, or None when no metric does.
#: The None rows are the Phase 2 backlog, in the plan's own words.
CAPABILITIES: dict[str, str | None] = {
    # --- provided today --------------------------------------------------
    "valuation_multiples": "valuation_score",
    "fundamentals_snapshot": "fundamentals",
    "price_trend": "momentum",
    "trend_state": "moving_average_state",
    "return_and_volatility": "return_stats",
    "volatility_shift": "volatility_regime",
    "drawdown_history": "drawdown_profile",
    "range_position": "range_position",
    "technical_levels": "technicals",
    "news_tone": "news_sentiment",
    "data_quality_flags": "risk_flags",
    "market_regime": "regime_clustering",
    "composite_view": "weighted_conviction",
    # --- from the annual statements, added in Phase 2 ---------------------
    "margin_trend": "margin_trend",
    "revenue_growth_history": "revenue_growth",
    "cash_conversion": "cash_conversion",
    "balance_sheet_strength": "balance_sheet",
    "capital_return": "capital_return",
    "operating_leverage": "operating_leverage",
    # --- comparisons with something outside the company, Phase 2 ---------
    "peer_comparison": "peer_comparison",
    "event_study": "event_study",
    "macro_sensitivity": "macro_sensitivity",
    # --- anything else: a planner-written formula, Phase 2 ----------------
    "custom_formula": "formula",
}


@dataclass(frozen=True)
class Question:
    id: str
    ticker: str
    question: str
    needs: tuple[str, ...]


QUESTIONS: tuple[Question, ...] = (
    # --- Apple ---------------------------------------------------------
    Question(
        "aapl-attractive",
        "AAPL",
        "Is this an attractive investment at current levels?",
        ("valuation_multiples", "price_trend", "composite_view"),
    ),
    Question(
        "aapl-downside",
        "AAPL",
        "What is the downside risk over the next year?",
        ("drawdown_history", "return_and_volatility", "volatility_shift"),
    ),
    Question(
        "aapl-expensive",
        "AAPL",
        "Is the stock expensive against its own growth?",
        ("valuation_multiples", "revenue_growth_history"),
    ),
    Question(
        "aapl-buybacks",
        "AAPL",
        "How much of the return comes from buybacks rather than growth?",
        ("capital_return", "revenue_growth_history"),
    ),
    Question(
        "aapl-margins", "AAPL", "Are services margins lifting the group margin?", ("margin_trend",)
    ),
    Question(
        "aapl-peers",
        "AAPL",
        "How does its valuation compare with Microsoft and Alphabet?",
        ("valuation_multiples", "peer_comparison"),
    ),
    # --- Expand Energy -------------------------------------------------
    Question(
        "exe-gas",
        "EXE",
        "How sensitive is the stock to the natural gas price?",
        ("macro_sensitivity",),
    ),
    Question(
        "exe-trend",
        "EXE",
        "Is the trend still intact after the recent move?",
        ("price_trend", "trend_state", "range_position"),
    ),
    Question(
        "exe-balance",
        "EXE",
        "Can the balance sheet carry a year of low gas prices?",
        ("balance_sheet_strength", "cash_conversion"),
    ),
    Question(
        "exe-vol",
        "EXE",
        "Has volatility changed regime recently?",
        ("volatility_shift", "market_regime"),
    ),
    Question(
        "exe-cheap",
        "EXE",
        "Is it cheap on the numbers?",
        ("valuation_multiples", "fundamentals_snapshot"),
    ),
    Question(
        "exe-shock",
        "EXE",
        "How did the stock behave in past gas-price shocks?",
        ("event_study", "macro_sensitivity"),
    ),
    # --- Lululemon -----------------------------------------------------
    Question(
        "lulu-falling-knife",
        "LULU",
        "Is this a falling knife or a value opportunity?",
        ("drawdown_history", "valuation_multiples", "price_trend"),
    ),
    Question(
        "lulu-margins",
        "LULU",
        "Are gross margins holding up as growth slows?",
        ("margin_trend", "revenue_growth_history"),
    ),
    Question("lulu-news", "LULU", "Is the news flow getting better or worse?", ("news_tone",)),
    Question(
        "lulu-near-low",
        "LULU",
        "How close is it to its 52-week low, and is it still falling?",
        ("range_position", "price_trend"),
    ),
    Question(
        "lulu-cash",
        "LULU",
        "Does the business still convert earnings into cash?",
        ("cash_conversion",),
    ),
    Question(
        "lulu-peers",
        "LULU",
        "How does it compare with Nike on growth and valuation?",
        ("peer_comparison", "revenue_growth_history", "valuation_multiples"),
    ),
    # --- Kohl's --------------------------------------------------------
    Question(
        "kss-survive",
        "KSS",
        "Can the company service its debt through a weak year?",
        ("balance_sheet_strength", "cash_conversion"),
    ),
    Question("kss-dividend", "KSS", "Is the dividend safe?", ("capital_return", "cash_conversion")),
    Question(
        "kss-value-trap",
        "KSS",
        "Is the low multiple a value trap?",
        ("valuation_multiples", "revenue_growth_history", "margin_trend"),
    ),
    Question(
        "kss-risk",
        "KSS",
        "What are the main risks in the data?",
        ("data_quality_flags", "drawdown_history", "volatility_shift"),
    ),
    Question(
        "kss-technicals",
        "KSS",
        "Where are the technical levels to watch?",
        ("technical_levels", "trend_state"),
    ),
    Question(
        "kss-leverage",
        "KSS",
        "How much would profit rise if sales recovered by 5%?",
        ("operating_leverage",),
    ),
    # --- Molson Coors --------------------------------------------------
    Question(
        "tap-defensive",
        "TAP",
        "Is this a defensive holding in a downturn?",
        ("return_and_volatility", "drawdown_history", "market_regime"),
    ),
    Question(
        "tap-attractive",
        "TAP",
        "Is this an attractive investment at current levels?",
        ("valuation_multiples", "price_trend", "composite_view"),
    ),
    Question(
        "tap-volume",
        "TAP",
        "Are volumes falling faster than price rises can offset?",
        ("revenue_growth_history", "margin_trend"),
    ),
    Question(
        "tap-rates",
        "TAP",
        "How does the stock respond to changes in interest rates?",
        ("macro_sensitivity", "event_study"),
    ),
    Question("tap-momentum", "TAP", "Has momentum turned?", ("price_trend", "trend_state")),
    Question(
        "tap-sentiment", "TAP", "What is the market saying about it in the news?", ("news_tone",)
    ),
    # --- no metric answers these directly: the planner must write a formula ---
    Question(
        "aapl-equity-per-share",
        "AAPL",
        "Has book value per share grown over the last three years?",
        ("custom_formula",),
    ),
    Question(
        "aapl-dividend-share",
        "AAPL",
        "What share of free cash flow was paid out as dividends last year?",
        ("custom_formula",),
    ),
    Question(
        "kss-payback",
        "KSS",
        "How many years of free cash flow would it take to repay the net debt?",
        ("custom_formula", "balance_sheet_strength"),
    ),
    Question(
        "kss-interest-burden",
        "KSS",
        "How much of operating profit is eaten by interest?",
        ("custom_formula",),
    ),
    Question(
        "lulu-capex-vs-sales",
        "LULU",
        "Is capital spending growing faster than revenue?",
        ("custom_formula", "revenue_growth_history"),
    ),
    Question(
        "exe-debt-trend",
        "EXE",
        "How fast has total debt changed over three years?",
        ("custom_formula",),
    ),
    Question(
        "tap-profit-vs-sales",
        "TAP",
        "Has operating profit grown faster than revenue over three years?",
        ("custom_formula", "revenue_growth_history"),
    ),
    Question(
        "lulu-cash-per-share",
        "LULU",
        "How much free cash flow does each share earn now, against three years ago?",
        ("custom_formula",),
    ),
)


def covered(q: Question) -> bool:
    """Every capability the question needs has a registered metric."""
    return all(CAPABILITIES.get(n) is not None for n in q.needs)


def coverage() -> dict[str, object]:
    """Share of the set the catalog can answer, and what blocks the rest."""
    blocked: dict[str, int] = {}
    for q in QUESTIONS:
        for n in q.needs:
            if CAPABILITIES.get(n) is None:
                blocked[n] = blocked.get(n, 0) + 1
    n_cov = sum(1 for q in QUESTIONS if covered(q))
    return {
        "covered": n_cov,
        "total": len(QUESTIONS),
        "share": round(n_cov / len(QUESTIONS), 3),
        "blocked_by": dict(sorted(blocked.items(), key=lambda kv: -kv[1])),
    }
