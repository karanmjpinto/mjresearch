"""News sentiment aggregation and evaluation alignment (no FinBERT runtime)."""

from __future__ import annotations

from hedge_fund.agents.evaluation import evaluate_research
from hedge_fund.agents.schemas import ResearchAnalysisOutput
from hedge_fund.nlp.news_sentiment import aggregate_scores


def test_aggregate_scores_empty():
    a = aggregate_scores([])
    assert a["article_count"] == 0
    assert a["mean_signed"] is None


def test_aggregate_scores_mixed():
    rows = [
        {"sentiment_label": "positive", "sentiment_score": 0.9},
        {"sentiment_label": "negative", "sentiment_score": 0.8},
        {"sentiment_label": "neutral", "sentiment_score": 0.7},
    ]
    a = aggregate_scores(rows)
    assert a["article_count"] == 3
    assert a["mean_signed"] is not None
    assert -1 <= a["mean_signed"] <= 1


def test_evaluate_research_sentiment_divergence_high_conviction_negative_news():
    out = ResearchAnalysisOutput(
        conviction_score=75,
        stance="BUY",
        investment_thesis="x" * 100,
        bull_case="a",
        bear_case="b",
        key_risks=[],
        time_horizon="medium_term",
        confidence_in_data=4,
    )
    snap = {
        "news_sentiment": {
            "enabled": True,
            "aggregate": {
                "article_count": 3,
                "mean_signed": -0.35,
                "positive_ratio": 0.1,
                "negative_ratio": 0.7,
                "neutral_ratio": 0.2,
            },
        }
    }
    ev = evaluate_research(out, data_snapshot=snap)
    notes = " ".join(ev["notes"])
    assert "news sentiment" in notes.lower() or "verify thesis" in notes.lower()


def test_evaluate_research_no_sentiment_skips():
    out = ResearchAnalysisOutput(
        conviction_score=50,
        stance="HOLD",
        investment_thesis="x" * 100,
        bull_case="a",
        bear_case="b",
        key_risks=[],
        time_horizon="medium_term",
        confidence_in_data=3,
    )
    ev = evaluate_research(out, data_snapshot={})
    assert not any("news sentiment" in n.lower() for n in ev["notes"])
