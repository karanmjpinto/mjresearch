"""Typed analysis plans: registry signatures, validation, execution, caching."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hedge_fund.plan import (
    AnalysisPlan,
    MetricError,
    PlanValidationError,
    catalog,
    execute_plan,
    get_metric,
    plan_hash,
    render_facts_for_prompt,
    topological_order,
    validate_plan,
)


class FakeDS:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def get_price_history(self, ticker, days=365, end_date=None):
        self.calls.append(days)
        n = min(int(days), 600)
        idx = pd.date_range("2025-01-01", periods=n, freq="D")
        rng = np.random.default_rng(0)
        px = 100 * np.exp(np.cumsum(rng.normal(0.0006, 0.015, n)))
        return pd.DataFrame({"close": px}, index=idx)


SNAP = {
    "ticker": "AAPL",
    "price": {"current": 316.83},
    "fundamentals": {
        "pe_ratio": 31.2,
        "price_to_book": 58.3,
        "peg_ratio": 2.1,
        "beta": 1.09,
        "52w_high": 355.0,
        "52w_low": 240.1,
        "currency": "USD",
        "sector": "Technology",
    },
    "technicals": {
        "rsi_14": 47.3,
        "sma_50": 320.0,
        "sma_200": 295.5,
        "price": 316.83,
        "atr_14": 6.2,
    },
    "news_sentiment": {"enabled": True, "aggregate": {"mean_signed": 0.12, "article_count": 5}},
    "provenance": {"warnings": []},
}


def _plan(*nodes, **kw):
    return AnalysisPlan(nodes=list(nodes), **kw)


def _run(plan, snapshot=SNAP, ds=None, cache=None):
    return execute_plan(plan, "AAPL", snapshot, data_service=ds or FakeDS(), value_cache=cache)


# ----------------------------------------------------------------------
# Registry contract
# ----------------------------------------------------------------------


def test_every_metric_declares_described_outputs():
    for spec in catalog():
        assert spec["outputs"], f"{spec['metric']} declares no outputs"
        for field in spec["outputs"]:
            assert field["description"].strip(), (
                f"{spec['metric']}.{field['name']} has no description"
            )


def test_every_param_is_described_and_bounded():
    for spec in catalog():
        for p in spec["params"]:
            assert p["description"].strip()
            if p["type"] in ("number", "integer"):
                assert "minimum" in p and "maximum" in p, f"{spec['metric']}.{p['name']} unbounded"


def test_metric_output_must_match_its_signature():
    metric = get_metric("valuation_score")
    with pytest.raises(MetricError, match="omitted declared field"):
        metric.validate_output({"valuation_score": 50})
    with pytest.raises(MetricError, match="undeclared field"):
        metric.validate_output(
            {
                "valuation_score": 50,
                "label": "fair",
                "inputs_used": "pe",
                "input_count": 1,
                "surprise": 1,
            }
        )


def test_unknown_metric_is_rejected():
    with pytest.raises(MetricError, match="unknown metric"):
        get_metric("does_not_exist")


# ----------------------------------------------------------------------
# Plan validation
# ----------------------------------------------------------------------


def test_valid_plan_passes():
    plan = _plan(
        {"id": "f", "metric": "fundamentals"},
        {"id": "v", "metric": "valuation_score", "depends_on": ["f"]},
    )
    assert validate_plan(plan) is plan


def test_empty_plan_is_rejected():
    with pytest.raises(PlanValidationError, match="no nodes"):
        validate_plan(_plan())


def test_duplicate_node_ids_rejected():
    with pytest.raises(PlanValidationError, match="duplicate node id"):
        validate_plan(
            _plan({"id": "a", "metric": "fundamentals"}, {"id": "a", "metric": "technicals"})
        )


def test_unknown_metric_rejected_at_plan_time():
    with pytest.raises(PlanValidationError, match="unknown metric"):
        validate_plan(_plan({"id": "a", "metric": "nope"}))


def test_bad_param_rejected_at_plan_time():
    with pytest.raises(PlanValidationError, match="must be >="):
        validate_plan(_plan({"id": "a", "metric": "price_window", "params": {"days": 1}}))


def test_unknown_param_rejected_at_plan_time():
    with pytest.raises(PlanValidationError, match="unknown parameter"):
        validate_plan(_plan({"id": "a", "metric": "price_window", "params": {"weeks": 4}}))


def test_unknown_dependency_rejected():
    with pytest.raises(PlanValidationError, match="unknown node"):
        validate_plan(_plan({"id": "a", "metric": "fundamentals", "depends_on": ["ghost"]}))


def test_self_dependency_rejected():
    with pytest.raises(PlanValidationError, match="depends on itself"):
        validate_plan(_plan({"id": "a", "metric": "fundamentals", "depends_on": ["a"]}))


def test_cycle_rejected():
    with pytest.raises(PlanValidationError, match="cycle"):
        validate_plan(
            _plan(
                {"id": "a", "metric": "fundamentals", "depends_on": ["b"]},
                {"id": "b", "metric": "technicals", "depends_on": ["a"]},
            )
        )


def test_clarification_affecting_unknown_node_rejected():
    with pytest.raises(PlanValidationError, match="affects unknown node"):
        validate_plan(
            _plan(
                {"id": "a", "metric": "fundamentals"},
                clarifications=[{"id": "c", "question": "?", "affects": ["ghost"]}],
            )
        )


def test_topological_order_respects_dependencies():
    plan = _plan(
        {"id": "c", "metric": "valuation_score", "depends_on": ["a"]},
        {"id": "a", "metric": "fundamentals"},
    )
    assert [n.id for n in topological_order(plan)] == ["a", "c"]


# ----------------------------------------------------------------------
# Execution
# ----------------------------------------------------------------------


def test_executes_all_nodes():
    plan = _plan(
        {"id": "val", "metric": "valuation_score"},
        {"id": "ma", "metric": "moving_average_state"},
        {"id": "rng", "metric": "range_position"},
    )
    ex = _run(plan)
    assert ex["ok_count"] == 3
    assert ex["error_count"] == 0
    assert ex["facts"]["valuation_score"] == 28


def test_conviction_is_reproducible_from_the_plan():
    plan = _plan(
        {"id": "val", "metric": "valuation_score"},
        {"id": "mom", "metric": "momentum", "params": {"lookback_days": 252}},
        {"id": "conv", "metric": "weighted_conviction", "depends_on": ["val", "mom"]},
    )
    a = _run(plan)["facts"]["conviction_score"]
    b = _run(plan)["facts"]["conviction_score"]
    assert a == b


def test_weights_change_the_conviction():
    def build(vw):
        return _plan(
            {"id": "val", "metric": "valuation_score"},
            {"id": "mom", "metric": "momentum", "params": {"lookback_days": 252}},
            {
                "id": "conv",
                "metric": "weighted_conviction",
                "params": {"valuation_weight": vw, "momentum_weight": 1.0},
                "depends_on": ["val", "mom"],
            },
        )

    assert (
        _run(build(0.1))["facts"]["conviction_score"]
        != _run(build(9.0))["facts"]["conviction_score"]
    )


def test_failing_node_does_not_abort_the_plan():
    snap = {**SNAP, "fundamentals": {"error": "no data"}}
    plan = _plan(
        {"id": "f", "metric": "fundamentals"},
        {"id": "ma", "metric": "moving_average_state"},
    )
    ex = _run(plan, snapshot=snap)
    assert ex["error_count"] == 1
    assert ex["ok_count"] == 1
    failed = next(n for n in ex["nodes"] if n["node_id"] == "f")
    assert "fundamentals unavailable" in failed["error"]


def test_dependants_of_a_failed_node_are_skipped_not_run():
    snap = {**SNAP, "fundamentals": {"error": "no data"}}
    plan = _plan(
        {"id": "val", "metric": "valuation_score"},
        {"id": "conv", "metric": "weighted_conviction", "depends_on": ["val"]},
    )
    ex = _run(plan, snapshot=snap)
    conv = next(n for n in ex["nodes"] if n["node_id"] == "conv")
    assert conv["status"] == "skipped"
    assert "depends on failed node" in conv["error"]


def test_plan_with_every_node_failing_reports_zero_ok():
    plan = _plan({"id": "f", "metric": "fundamentals"})
    ex = _run(plan, snapshot={"fundamentals": {"error": "gone"}})
    assert ex["ok_count"] == 0


def test_value_cache_prevents_recomputation():
    cache: dict = {}
    plan = _plan({"id": "val", "metric": "valuation_score"})
    first = _run(plan, cache=cache)
    second = _run(plan, cache=cache)
    assert first["cache_hits"] == 0
    assert second["cache_hits"] == 1


def test_editing_one_node_reuses_the_others():
    """A changed node must not force its independent siblings to recompute."""
    cache: dict = {}
    ds = FakeDS()
    base = _plan(
        {"id": "val", "metric": "valuation_score"},
        {"id": "mom", "metric": "momentum", "params": {"lookback_days": 252}},
    )
    _run(base, ds=ds, cache=cache)
    edited = _plan(
        {"id": "val", "metric": "valuation_score"},
        {"id": "mom", "metric": "momentum", "params": {"lookback_days": 90}},
    )
    ex = _run(edited, ds=ds, cache=cache)
    assert ex["cache_hits"] == 1  # valuation reused, momentum recomputed


def test_price_frame_is_fetched_once_per_window():
    ds = FakeDS()
    plan = _plan(
        {"id": "r", "metric": "return_stats", "params": {"days": 365}},
        {"id": "d", "metric": "drawdown_profile", "params": {"days": 365}},
    )
    _run(plan, ds=ds)
    assert ds.calls.count(365) == 1


def test_plan_hash_is_stable_and_content_sensitive():
    a = _plan({"id": "x", "metric": "price_window", "params": {"days": 90}, "why": "one"})
    b = _plan(
        {"id": "x", "metric": "price_window", "params": {"days": 90}, "why": "different prose"}
    )
    c = _plan({"id": "x", "metric": "price_window", "params": {"days": 91}})
    assert plan_hash(a) == plan_hash(b), "prose should not change the plan identity"
    assert plan_hash(a) != plan_hash(c), "parameters should change the plan identity"


def test_execution_is_deterministic():
    plan = _plan(
        {"id": "val", "metric": "valuation_score"},
        {"id": "ret", "metric": "return_stats", "params": {"days": 365}},
    )
    assert _run(plan)["facts"] == _run(plan)["facts"]


def test_weighted_conviction_without_dimensions_fails_clearly():
    plan = _plan({"id": "conv", "metric": "weighted_conviction"})
    ex = _run(plan, snapshot={"fundamentals": {}, "technicals": {}})
    assert ex["error_count"] == 1
    assert "no dimension scores" in ex["nodes"][0]["error"]


# ----------------------------------------------------------------------
# Fact rendering
# ----------------------------------------------------------------------


def test_rendered_facts_include_values_and_failures():
    snap = {**SNAP, "fundamentals": {"error": "no data"}}
    plan = _plan(
        {"id": "f", "metric": "fundamentals"},
        {"id": "ma", "metric": "moving_average_state", "why": "trend check"},
    )
    text = render_facts_for_prompt(_run(plan, snapshot=snap))
    assert "NOT AVAILABLE" in text
    assert "trend check" in text


def test_rendered_facts_disclose_unconfirmed_defaults():
    plan = _plan(
        {"id": "mom", "metric": "momentum"},
        clarifications=[
            {
                "id": "skip",
                "question": "Skip the last month?",
                "options": ["yes", "no"],
                "recommended": "yes",
                "affects": ["mom"],
            }
        ],
    )
    text = render_facts_for_prompt(_run(plan))
    assert "default, not confirmed by the user" in text
