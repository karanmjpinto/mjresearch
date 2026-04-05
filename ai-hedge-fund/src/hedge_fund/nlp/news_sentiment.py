"""Financial news sentiment via ProsusAI/finbert (Hugging Face transformers).

Install optional deps: `uv sync --extra sentiment`. If missing or disabled, returns
pass-through news with news_sentiment.enabled=false.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from typing import Any

from hedge_fund.settings import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_pipeline = None


def _label_sign(label: str) -> int:
    """Map model label to -1 / 0 / +1."""
    s = (label or "").lower()
    if "positive" in s:
        return 1
    if "negative" in s:
        return -1
    return 0


def _truncate(text: str, max_chars: int = 480) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _get_pipeline():
    global _pipeline
    with _lock:
        if _pipeline is None:
            from transformers import pipeline

            mid = settings.finbert_model_id
            _pipeline = pipeline(
                "sentiment-analysis",
                model=mid,
                tokenizer=mid,
                device=-1,
                truncation=True,
                max_length=512,
            )
        return _pipeline


def aggregate_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure aggregation for tests — rows have sentiment_label, sentiment_score (0–1)."""
    if not rows:
        return {
            "article_count": 0,
            "mean_signed": None,
            "positive_ratio": None,
            "negative_ratio": None,
            "neutral_ratio": None,
        }
    signs = []
    pos_n = neg_n = neu_n = 0
    for r in rows:
        lbl = str(r.get("sentiment_label") or "")
        conf = float(r.get("sentiment_score") or 0.0)
        sg = _label_sign(lbl)
        signs.append(sg * conf)
        ls = lbl.lower()
        if "positive" in ls:
            pos_n += 1
        elif "negative" in ls:
            neg_n += 1
        else:
            neu_n += 1
    n = len(rows)
    return {
        "article_count": n,
        "mean_signed": round(sum(signs) / n, 4),
        "positive_ratio": round(pos_n / n, 3),
        "negative_ratio": round(neg_n / n, 3),
        "neutral_ratio": round(neu_n / n, 3),
    }


def enrich_news_with_sentiment(
    news_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Score each article's title with FinBERT. Returns (enriched list, summary dict).

    news_items: dicts with at least 'title' (and optional 'date').
    """
    if not settings.news_sentiment_enabled:
        return news_items, {
            "enabled": False,
            "reason": "disabled_in_settings",
            "model": None,
            "aggregate": aggregate_scores([]),
        }

    try:
        pipe = _get_pipeline()
    except ImportError:
        logger.info(
            "News sentiment skipped: install optional deps with `uv sync --extra sentiment`"
        )
        return news_items, {
            "enabled": False,
            "reason": "transformers_not_installed",
            "model": None,
            "aggregate": aggregate_scores([]),
        }
    except Exception as e:
        logger.exception("News sentiment pipeline init failed: %s", e)
        return news_items, {
            "enabled": False,
            "reason": f"init_error: {e!s}",
            "model": settings.finbert_model_id,
            "aggregate": aggregate_scores([]),
        }

    if not news_items:
        return news_items, {
            "enabled": True,
            "reason": None,
            "model": settings.finbert_model_id,
            "aggregate": aggregate_scores([]),
        }

    texts: list[str] = []
    for item in news_items:
        raw = str(item.get("title") or "")
        # Strip obvious HTML / noise
        raw = re.sub(r"<[^>]+>", " ", raw)
        texts.append(_truncate(raw))

    try:
        preds = pipe(texts)
    except Exception as e:
        logger.exception("FinBERT inference failed: %s", e)
        return news_items, {
            "enabled": False,
            "reason": f"inference_error: {e!s}",
            "model": settings.finbert_model_id,
            "aggregate": aggregate_scores([]),
        }

    enriched: list[dict[str, Any]] = []
    for item, pred in zip(news_items, preds, strict=True):
        row = dict(item)
        lbl = str(pred.get("label", ""))
        sc = float(pred.get("score", 0.0))
        row["sentiment_label"] = lbl
        row["sentiment_score"] = round(sc, 4)
        enriched.append(row)

    summary = {
        "enabled": True,
        "reason": None,
        "model": settings.finbert_model_id,
        "aggregate": aggregate_scores(enriched),
    }
    return enriched, summary


async def enrich_news_with_sentiment_async(
    news_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run CPU-bound FinBERT in a thread pool."""
    return await asyncio.to_thread(enrich_news_with_sentiment, news_items)
