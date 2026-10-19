"""The `formula` step: a planner-written expression, checked and computed by code.

See `plan/formula.py` for the language. This module only registers it.
"""

from __future__ import annotations

from typing import Any

from hedge_fund.plan import formula
from hedge_fund.plan.registry import _round, _snapshot_value, register
from hedge_fund.plan.types import FieldSpec, Metric, ParamSpec


def _check(params: dict[str, Any], upstream: dict[str, str]) -> list[str]:
    problems = []
    if not formula.valid_name(params["name"]):
        problems.append("name must be lower_snake_case, e.g. fcf_to_net_income_pct")
    return problems + formula.check(params["expression"], upstream)


def _formula(ctx: Any, name: str, expression: str, unit: str, description: str) -> dict[str, Any]:
    table = _snapshot_value(ctx, "statements") or {}
    series = table.get("series") or {} if isinstance(table, dict) else {}
    value = formula.evaluate(expression, series, ctx.facts)
    return {
        "formula_name": name,
        "formula_value": _round(value, 4),
        "formula_unit": unit,
        "formula_expression": expression,
    }


_FUNCS = "; ".join(formula.DESCRIPTIONS.values())

register(
    Metric(
        id="formula",
        label="Formula",
        description="A measure no other metric provides, written as a formula over the annual "
        "statement series and values earlier steps computed. Checked before it runs; computed "
        f"by code. Functions: {_FUNCS}. Arithmetic: + - * / and parentheses. Nothing else. "
        "Inside a function, series combine year by year: change(equity / shares, 3) is the "
        "three-year change in book value per share. A bare series in arithmetic means its "
        "latest year.",
        tier="evaluate",
        params=(
            ParamSpec(
                "name",
                "string",
                "lower_snake_case name for the result, e.g. "
                "fcf_to_net_income_pct. End it in _pct when the unit is %.",
                required=True,
            ),
            ParamSpec(
                "expression",
                "string",
                "The formula, e.g. 'pct(latest(free_cash_flow), latest(net_income))'.",
                required=True,
            ),
            ParamSpec(
                "unit",
                "string",
                "Unit of the result.",
                default="number",
                choices=("%", "x", "currency", "number"),
            ),
            ParamSpec(
                "description", "string", "One line saying what the result means.", default=""
            ),
        ),
        outputs=(
            FieldSpec("formula_name", "string", "The name given to the result"),
            FieldSpec("formula_value", "number", "The computed result"),
            FieldSpec("formula_unit", "string", "Unit of the result"),
            FieldSpec("formula_expression", "string", "The formula as written"),
        ),
        consumes=("values from the steps it depends on",),
        notes="Series: " + ", ".join(sorted(formula.SERIES)) + ". A value from another step "
        "may be used only if this step depends on that step.",
        check=_check,
        fn=_formula,
    )
)
