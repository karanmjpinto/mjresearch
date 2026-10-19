"""Annual statements: the table that aligns them and the metrics that read them."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from hedge_fund.data.statements import build_table
from hedge_fund.plan import AnalysisPlan, execute_plan

Y = [pd.Timestamp(f"{y}-12-31") for y in (2025, 2024, 2023, 2022)]


def _frame(rows: dict[str, list[float | None]], cols=Y) -> pd.DataFrame:
    return pd.DataFrame(rows, index=cols).T


def _table(**series: list[float | None]) -> dict:
    periods = ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"]
    base = {
        k: [None] * 4
        for k in (
            "revenue",
            "gross_profit",
            "operating_income",
            "net_income",
            "ebitda",
            "interest_expense",
            "depreciation",
            "operating_cash_flow",
            "capex",
            "free_cash_flow",
            "buybacks",
            "dividends",
            "total_debt",
            "cash",
            "equity",
            "shares",
        )
    }
    base.update(series)
    return {"currency": "USD", "frequency": "annual", "periods": periods, "series": base}


def _run(metric: str, table: dict, **params):
    plan = AnalysisPlan(nodes=[{"id": "n", "metric": metric, "params": params}])
    node = execute_plan(plan, "TEST", {"statements": table})["nodes"][0]
    return node


# --- the table --------------------------------------------------------


def test_a_year_missing_from_one_statement_stays_in_its_place():
    """Pairing what is left after dropping a gap is how a year silently shifts."""
    income = _frame({"Total Revenue": [400.0, 390.0, 380.0, 370.0]})
    cash = _frame({"Free Cash Flow": [90.0, 80.0]}, cols=[Y[0], Y[2]])
    t = build_table({"income": income, "cashflow": cash, "balance": None})
    assert t["series"]["free_cash_flow"] == [90.0, None, 80.0, None]


def test_share_counts_are_adjusted_for_later_splits():
    income = _frame({"Total Revenue": [1.0, 1.0, 1.0, 1.0]})
    bal = _frame({"Ordinary Shares Number": [400.0, 400.0, 100.0, 100.0]})
    splits = pd.Series([4.0], index=[pd.Timestamp("2024-06-01", tz="UTC")])
    t = build_table({"income": income, "balance": bal}, splits)
    assert t["series"]["shares"] == [400.0, 400.0, 400.0, 400.0]


def test_a_year_is_not_used_before_its_accounts_were_public():
    income = _frame({"Total Revenue": [4.0, 3.0, 2.0, 1.0]})
    t = build_table({"income": income}, end_date=date(2026, 2, 1))
    assert t["periods"][0] == "2024-12-31"  # FY2025 closed 32 days earlier


# --- the metrics ------------------------------------------------------


def test_revenue_growth_is_compound_and_says_how_many_years_it_spans():
    v = _run("revenue_growth", _table(revenue=[133.1, 121.0, 110.0, 100.0]), years=3)["values"]
    assert v["revenue_cagr_pct"] == pytest.approx(10.0, abs=0.01)
    assert v["revenue_years_used"] == 3 and v["revenue_declining_years"] == 0


def test_latest_means_the_latest_year_never_an_older_one_standing_in():
    """Seen on AAPL: interest cover was this year's profit over 2023's interest."""
    t = _table(
        operating_income=[100.0, 90.0, 80.0, 70.0],
        interest_expense=[None, None, 4.0, 3.0],
        total_debt=[50.0] * 4,
        cash=[10.0] * 4,
    )
    assert _run("balance_sheet", t)["values"]["interest_cover"] is None


def test_operating_leverage_is_refused_for_a_loss_maker_not_scored_as_infinite():
    t = _table(operating_income=[-5.0, 3.0, 2.0, 1.0], gross_profit=[20.0] * 4, revenue=[100.0] * 4)
    node = _run("operating_leverage", t)
    assert node["status"] == "error" and "not positive" in node["error"]


def test_operating_leverage_matches_the_textbook_case():
    """Revenue 100: 30 variable, 55 fixed, 15 profit. Contribution 70, so 4.67."""
    t = _table(
        revenue=[100.0, 90.0, None, None],
        gross_profit=[70.0, 63.0, None, None],
        operating_income=[15.0, 8.0, None, None],
        depreciation=[0.0, 0.0, None, None],
    )
    v = _run("operating_leverage", t, sales_change_pct=10.0)["values"]
    assert v["degree_of_operating_leverage"] == pytest.approx(4.67, abs=0.01)
    assert v["profit_change_for_sales_change_pct"] == pytest.approx(46.7, abs=0.1)


def test_capital_return_reads_outflows_as_reported_and_shrinking_shares_as_negative():
    t = _table(
        shares=[90.0, 95.0, 100.0, None],
        buybacks=[-60.0, None, None, None],
        dividends=[-20.0, None, None, None],
        free_cash_flow=[100.0, None, None, None],
    )
    v = _run("capital_return", t)["values"]
    assert v["buybacks_latest"] == 60.0 and v["payout_to_fcf_pct"] == 80.0
    assert v["share_count_change_pct_per_year"] < 0 and v["share_years_used"] == 2


def test_cash_conversion_is_summed_across_years_not_one_noisy_year():
    t = _table(
        free_cash_flow=[50.0, 150.0, None, None],
        net_income=[100.0, 100.0, None, None],
        revenue=[1000.0, 1000.0, None, None],
    )
    v = _run("cash_conversion", t)["values"]
    assert v["fcf_to_net_income"] == 1.0 and v["cash_years_used"] == 2


def test_a_snapshot_without_statements_reports_the_gap():
    node = execute_plan(AnalysisPlan(nodes=[{"id": "n", "metric": "margin_trend"}]), "T", {})[
        "nodes"
    ][0]
    assert node["status"] == "error" and "statements unavailable" in node["error"]
