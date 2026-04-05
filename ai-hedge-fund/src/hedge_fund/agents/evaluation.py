"""Lightweight post-hoc checks on LLM output (not a second model)."""

from __future__ import annotations

from typing import Any

from hedge_fund.agents.schemas import ResearchAnalysisOutput


def evaluate_research(
    output: ResearchAnalysisOutput,
    *,
    data_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Heuristic checks: stance vs conviction alignment, data presence."""
    checks: dict[str, Any] = {
        "stance_conviction_aligned": True,
        "notes": [],
    }
    c = output.conviction_score
    if output.stance == "SELL" and c > 70:
        checks["stance_conviction_aligned"] = False
        checks["notes"].append("SELL with high conviction score unusual")
    if output.stance == "BUY" and c < 30:
        checks["stance_conviction_aligned"] = False
        checks["notes"].append("BUY with very low conviction score")

    fund = data_snapshot.get("fundamentals") or {}
    if isinstance(fund, dict) and fund.get("error"):
        checks["notes"].append("fundamentals were missing in snapshot")

    ns = data_snapshot.get("news_sentiment")
    if not isinstance(ns, dict):
        ns = {}
    agg = ns.get("aggregate")
    if (
        ns.get("enabled")
        and isinstance(agg, dict)
        and agg.get("mean_signed") is not None
        and (agg.get("article_count") or 0) > 0
    ):
        mean_signed = float(agg["mean_signed"])
        c = output.conviction_score
        # Headline sentiment vs LLM conviction (FinBERT is noisy — soft thresholds)
        if mean_signed < -0.2 and c >= 60:
            checks["notes"].append(
                "news sentiment skews negative vs relatively high LLM conviction — verify thesis"
            )
        if mean_signed > 0.2 and c <= 40:
            checks["notes"].append(
                "news sentiment skews positive vs relatively low LLM conviction — verify thesis"
            )
        if output.stance in ("SELL", "HOLD") and mean_signed > 0.25 and c >= 55:
            checks["notes"].append(
                "bearish/neutral stance with bullish headline sentiment cluster — review"
            )

    checks["data_completeness_score"] = max(1, min(5, output.confidence_in_data))
    return checks
