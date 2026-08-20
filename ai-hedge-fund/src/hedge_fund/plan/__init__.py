"""Typed analysis plans: the model chooses metrics, the harness computes them."""

from hedge_fund.plan.executor import PlanContext, execute_plan, plan_hash, render_facts_for_prompt
from hedge_fund.plan.registry import all_metrics, catalog, get_metric, register
from hedge_fund.plan.schema import (
    AnalysisPlan,
    Clarification,
    PlanNode,
    PlanValidationError,
    topological_order,
    validate_plan,
)
from hedge_fund.plan.types import FieldSpec, Metric, MetricError, NodeResult, ParamSpec

__all__ = [
    "AnalysisPlan",
    "Clarification",
    "FieldSpec",
    "Metric",
    "MetricError",
    "NodeResult",
    "ParamSpec",
    "PlanContext",
    "PlanNode",
    "PlanValidationError",
    "all_metrics",
    "catalog",
    "execute_plan",
    "get_metric",
    "plan_hash",
    "register",
    "render_facts_for_prompt",
    "topological_order",
    "validate_plan",
]
