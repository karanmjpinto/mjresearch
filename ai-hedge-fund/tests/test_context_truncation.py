"""Context reduction must always emit valid JSON and disclose what it dropped."""

from __future__ import annotations

import json

import pytest

from hedge_fund.agents.context import build_bundle
from hedge_fund.agents.guardrails import truncate_context, truncate_context_with_manifest


def _snapshot(n_news: int = 40, thesis_len: int = 0) -> dict:
    snap = {
        "ticker": "AAPL",
        "price": {"current": 316.83, "change_30d_pct": -2.99},
        "fundamentals": {"pe_ratio": 31.2, "market_cap": 4.7e12, "currency": "USD"},
        "technicals": {"rsi_14": 47.3, "macd": -1.2},
        "news": [
            {"title": f"Headline number {i} about the company" * 3, "date": "2026-08-01"}
            for i in range(n_news)
        ],
        "news_sentiment": {"enabled": True, "aggregate": {"mean_signed": 0.1}},
        "provenance": {
            "slots": {f"cat{i}:AAPL": {"provider": "openbb", "checks": {}} for i in range(20)},
            "providers_used": ["openbb"],
            "warnings": ["fundamentals:AAPL: currency not declared"],
        },
    }
    if thesis_len:
        snap["long_field"] = "x" * thesis_len
    return snap


@pytest.mark.parametrize("limit", [200, 500, 1000, 2000, 4000, 8000, 24000])
def test_output_is_always_valid_json(limit):
    text = truncate_context(_snapshot(), max_chars=limit)
    json.loads(text)  # must not raise


@pytest.mark.parametrize("limit", [100, 200, 500, 1000, 2000, 4000, 8000])
def test_output_respects_the_limit(limit):
    text = truncate_context(_snapshot(), max_chars=limit)
    assert len(text) <= limit


def test_untruncated_snapshot_passes_through_unchanged():
    snap = {"ticker": "AAPL", "price": {"current": 1.0}}
    text, manifest = build_bundle(snap, 100_000)
    assert json.loads(text) == snap
    assert manifest == {"truncated": False}
    assert "_truncation" not in json.loads(text)


def test_ticker_and_price_survive_severe_truncation():
    text = truncate_context(_snapshot(n_news=200), max_chars=300)
    obj = json.loads(text)
    assert obj["ticker"] == "AAPL"
    assert "price" in obj


def test_manifest_names_what_was_dropped():
    _text, manifest = truncate_context_with_manifest(_snapshot(), max_chars=1200)
    assert manifest["truncated"] is not False
    assert manifest["dropped"], "something was dropped but the manifest is empty"
    assert any("news" in d or "provenance" in d for d in manifest["dropped"])


def test_model_is_told_truncation_is_not_absence():
    text = truncate_context(_snapshot(), max_chars=1200)
    obj = json.loads(text)
    assert "not as absent from the market" in obj["_truncation"]["note"]


def test_provenance_detail_is_dropped_before_news():
    """Slot detail is the cheapest thing to lose; headlines are not."""
    text = truncate_context(_snapshot(n_news=3), max_chars=1500)
    obj = json.loads(text)
    assert obj.get("provenance", {}).get("detail_omitted") is True
    assert obj.get("news"), "news was dropped before provenance detail"


def test_provenance_warnings_survive_slot_collapse():
    text = truncate_context(_snapshot(n_news=3), max_chars=1500)
    obj = json.loads(text)
    assert obj["provenance"]["warnings"]


def test_long_free_text_fields_are_capped_not_sliced_off():
    text = truncate_context(_snapshot(n_news=1, thesis_len=50_000), max_chars=4000)
    obj = json.loads(text)
    assert "field truncated" in obj["long_field"]


def test_reduction_is_deterministic():
    snap = _snapshot()
    a = truncate_context(snap, max_chars=2000)
    b = truncate_context(snap, max_chars=2000)
    assert a == b


def test_reduction_does_not_mutate_the_input_snapshot():
    snap = _snapshot()
    before = json.dumps(snap, default=str, sort_keys=True)
    truncate_context(snap, max_chars=500)
    assert json.dumps(snap, default=str, sort_keys=True) == before


def test_absurdly_small_limit_still_parses():
    """Below the useful floor we stop honouring the limit, but never the syntax."""
    text = truncate_context(_snapshot(), max_chars=20)
    obj = json.loads(text)
    assert obj["_truncation"]["severe"] is True
    assert obj["ticker"] == "AAPL"


def test_manifest_always_carries_a_truncated_flag():
    for limit in (100, 1200, 100_000):
        _t, manifest = truncate_context_with_manifest(_snapshot(), max_chars=limit)
        assert "truncated" in manifest
