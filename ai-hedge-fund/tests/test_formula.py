"""The formula language: what it accepts, what it refuses, what it computes.

The refusals matter most. The planner is a language model and its formulas
arrive as strings; the only thing standing between a string and execution is
the whitelist in `formula.check`, so each class of escape gets a test.
"""

from __future__ import annotations

import pytest

from hedge_fund.plan import AnalysisPlan, PlanValidationError, execute_plan, validate_plan
from hedge_fund.plan.formula import check, evaluate
from hedge_fund.plan.types import MetricError

SERIES = {
    "revenue": [133.1, 121.0, 110.0, 100.0],
    "net_income": [20.0, 18.0, None, 15.0],
    "free_cash_flow": [25.0, 18.0, 12.0, 10.0],
}


@pytest.mark.parametrize(
    "expr",
    [
        "pct(latest(free_cash_flow), latest(net_income))",
        "cagr(revenue, 3) - change(revenue, 1)",
        "(latest(revenue) - prior(revenue, 1)) / prior(revenue, 1) * 100",
        "-abs(gross_margin_pct) + 1.5",
        # Written the way the model writes them, normalised before the check:
        "interest_expense / operating_income",  # a bare series is its latest year
        "latest(gross_margin_pct)",  # latest of a value is the value
        "margin_trend.gross_margin_pct * 2",  # step.field is the field
        "change(equity / shares, 3)",  # year-by-year arithmetic on series
    ],
)
def test_ordinary_formulas_pass(expr):
    assert check(expr, {"gross_margin_pct"}) == []


@pytest.mark.parametrize(
    "expr, says",
    [
        ("__import__('os').system('ls')", "not allowed"),
        ("__import__('os')", "unknown function"),
        ("revenue.__class__", "not allowed"),
        ("SERIES['revenue']", "not allowed"),
        ("(lambda: 1)()", "not allowed"),
        ("latest(revenue) if 1 else 0", "not allowed"),
        ("latest(revenue) > 1", "compares"),
        ("'text'", "not allowed"),
        ("latest(revenue) ** 2", "not allowed"),
        ("made_up_value + 1", "not computed by any earlier step"),
        ("cagr(revenue, 9)", "whole number of years"),
        ("cagr(revenue, n=3)", "keyword"),
        ("pct(1)", "takes 2 argument"),
        ("latest(", "does not parse"),
    ],
)
def test_everything_outside_the_language_is_refused_with_a_reason(expr, says):
    problems = check(expr, {"gross_margin_pct"})
    assert problems and any(says in p for p in problems), problems


def test_growth_and_change_and_slope_compute_the_textbook_values():
    assert evaluate("cagr(revenue, 3)", SERIES, {}) == pytest.approx(10.0, abs=0.01)
    assert evaluate("change(revenue, 1)", SERIES, {}) == pytest.approx(10.0, abs=0.01)
    assert evaluate("slope(free_cash_flow, 3)", SERIES, {}) > 0  # rising is positive


def test_a_missing_year_fails_rather_than_counting_as_zero():
    with pytest.raises(MetricError, match="missing year"):
        evaluate("mean(net_income, 3)", SERIES, {})


def test_division_by_zero_is_a_failure_not_an_infinity():
    with pytest.raises(MetricError, match="division by zero"):
        evaluate("ratio(latest(revenue), 0)", SERIES, {})


def _plan(*nodes):
    return AnalysisPlan(nodes=list(nodes))


def test_a_formula_reads_values_only_from_steps_it_depends_on():
    plan = _plan(
        {"id": "m", "metric": "margin_trend"},
        {
            "id": "f",
            "metric": "formula",
            "params": {"name": "half_margin", "expression": "gross_margin_pct / 2"},
        },
    )
    with pytest.raises(PlanValidationError, match="not computed by any earlier step"):
        validate_plan(plan)
    plan.nodes[1].depends_on.append("m")
    validate_plan(plan)


def test_a_formula_result_is_filed_under_its_own_name_for_later_steps():
    snap = {
        "statements": {
            "periods": ["2025", "2024", "2023", "2022"],
            "series": {
                "revenue": SERIES["revenue"],
                "free_cash_flow": SERIES["free_cash_flow"],
                "net_income": [20.0, 18.0, 16.0, 15.0],
            },
        }
    }
    plan = _plan(
        {
            "id": "a",
            "metric": "formula",
            "params": {
                "name": "fcf_to_ni_pct",
                "expression": "pct(latest(free_cash_flow), latest(net_income))",
                "unit": "%",
            },
        },
        {
            "id": "b",
            "metric": "formula",
            "depends_on": ["a"],
            "params": {"name": "fcf_to_ni_gap", "expression": "fcf_to_ni_pct - 100"},
        },
    )
    ex = execute_plan(plan, "T", snap)
    assert ex["facts"]["fcf_to_ni_pct"] == 125.0
    assert ex["facts"]["fcf_to_ni_gap"] == 25.0


def test_the_harness_adds_a_dependency_a_formula_forgot():
    from hedge_fund.agents.plan_agent import resolve_dependency_names

    plan = _plan(
        {"id": "m", "metric": "margin_trend"},
        {
            "id": "f",
            "metric": "formula",
            "params": {"name": "half_margin", "expression": "gross_margin_pct / 2"},
        },
    )
    fixes = resolve_dependency_names(plan)
    assert {"node": "f", "uses": "gross_margin_pct", "added_dependency": "m"} in fixes
    validate_plan(plan)


def test_a_dunder_attribute_is_still_refused_after_normalising():
    assert check("revenue.__class__", set())
    assert check("margin_trend.__dict__", set())


def test_series_arithmetic_is_year_by_year():
    series = {"equity": [120.0, 110.0, 100.0, 90.0], "shares": [10.0, 10.0, 10.0, 12.0]}
    assert evaluate("change(equity / shares, 3)", series, {}) == pytest.approx(60.0)
    assert evaluate("latest(equity / shares)", series, {}) == 12.0


def test_a_bare_series_in_arithmetic_means_its_latest_year():
    assert evaluate("revenue / 2", SERIES, {}) == pytest.approx(66.55)


def test_an_unknown_unit_is_reset_by_the_harness_not_a_reason_to_fail():
    from hedge_fund.agents.plan_agent import resolve_dependency_names

    plan = _plan(
        {
            "id": "f",
            "metric": "formula",
            "params": {"name": "x_gap", "expression": "latest(revenue)", "unit": "boolean"},
        }
    )
    fixes = resolve_dependency_names(plan)
    assert plan.nodes[0].params["unit"] == "number"
    assert fixes == [{"node": "f", "wrote": "unit boolean", "resolved_to": "unit number"}]
    validate_plan(plan)


def test_a_formula_result_quoted_in_words_counts_as_cited():
    from hedge_fund.agents.verifier import verify_analysis

    snap = {
        "computed": {"total_debt_change_3y_pct": 59.1696},
        "formula_names": ["total_debt_change_3y_pct"],
    }
    cited = verify_analysis({"investment_thesis": "Debt rose 59.17% over three years."}, snap)
    assert cited["status"] == "clean"
    vague = verify_analysis({"investment_thesis": "Debt rose over 3 years, about 2x."}, snap)
    assert vague["status"] == "no_claims"


def test_a_wrong_name_gets_a_suggestion_the_repair_can_use():
    assert any("did you mean free_cash_flow" in p for p in check("latest(revenue) / fcf", set()))


def test_a_comparison_is_refused_with_what_to_write_instead():
    assert any(
        "subtract instead" in p for p in check("change(capex, 1) > change(revenue, 1)", set())
    )


def test_a_value_in_a_series_position_says_which_series_to_use():
    problems = check("change(fcf_per_share_now, 3)", {"fcf_per_share_now"})
    assert any("single value, not a series" in p for p in problems)


def test_an_unambiguous_wrong_name_is_corrected_and_an_ambiguous_one_is_not():
    from hedge_fund.agents.plan_agent import resolve_dependency_names

    plan = _plan(
        {
            "id": "f",
            "metric": "formula",
            "params": {"name": "payback_years", "expression": "latest(total_debt) / fcf"},
        }
    )
    fixes = resolve_dependency_names(plan)
    assert plan.nodes[0].params["expression"] == "latest(total_debt) / free_cash_flow"
    assert {"node": "f", "wrote": "fcf", "resolved_to": "free_cash_flow"} in fixes
    validate_plan(plan)


def test_a_negative_series_says_to_negate_it():
    with pytest.raises(MetricError, match="use -capex"):
        evaluate("change(capex, 1)", {"capex": [-10.0, -8.0, -7.0]}, {})


# --- units: the formulas that parsed, ran, and meant nothing -------------

UNITS = {"total_return_pct": "%", "pe_ratio": "", "revenue_cagr_pct": "%", "gross_margin_pct": "%"}


@pytest.mark.parametrize(
    "expr",
    [
        "pct(latest(buybacks), latest(total_return_pct))",  # dollars over percent, seen live
        "pct(change(free_cash_flow / shares, 3), prior(free_cash_flow / shares, 3))",  # seen live
        "latest(revenue) + gross_margin_pct",
        "latest(revenue) / revenue_cagr_pct",
    ],
)
def test_arithmetic_on_unlike_units_is_refused(expr):
    assert check(expr, UNITS), expr


@pytest.mark.parametrize(
    "expr",
    [
        "ratio(latest(pe_ratio), latest(revenue_cagr_pct))",  # PEG: a ratio over a growth rate
        "latest(equity / shares)",  # currency per share
        "pct(latest(dividends), latest(free_cash_flow))",  # a share of like things
        "100 - gross_margin_pct",  # a bare number takes the unit it meets
        "change(capex, 3) - change(revenue, 3)",  # two percentages
    ],
)
def test_meaningful_arithmetic_passes_the_unit_check(expr):
    assert check(expr, UNITS) == [], expr
