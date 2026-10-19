"""The capital-cycle reading: arriving, leaving, mixed, or not enough to say."""

from __future__ import annotations

from hedge_fund.data.capital_cycle import read
from hedge_fund.plan import AnalysisPlan, execute_plan


def _table(capex, dep, rev, op, shares):
    return {
        "periods": ["2025", "2024", "2023", "2022"],
        "series": {
            "capex": capex,
            "depreciation": dep,
            "revenue": rev,
            "operating_income": op,
            "shares": shares,
        },
    }


def test_a_memory_maker_at_peak_reads_as_capital_arriving():
    """SK hynix in the 2025 accounts: capex 2x depreciation, margin far above average."""
    t = _table(
        capex=[-20.0, -15.0, -12.0, -14.0],
        dep=[10.0, 10.0, 10.0, 10.0],
        rev=[100.0, 70.0, 40.0, 60.0],
        op=[48.0, 20.0, -10.0, 5.0],
        shares=[7.0, 7.0, 7.0, 7.0],
    )
    r = read(t)
    assert r["capital_cycle"] == "arriving"
    assert r["capex_to_depreciation"] == 2.0 and r["margin_vs_average_pp"] > 10


def test_a_wafer_maker_after_its_build_reads_as_capital_leaving():
    """SUMCO: capex back to depreciation from 2.1x, margin below its average."""
    t = _table(
        capex=[-10.0, -18.0, -15.0, -21.0],
        dep=[10.0, 10.0, 10.0, 10.0],
        rev=[100.0, 100.0, 110.0, 105.0],
        op=[1.0, 8.0, 20.0, 18.0],
        shares=[3.5, 3.5, 3.5, 3.5],
    )
    r = read(t)
    assert r["capital_cycle"] == "leaving"
    assert "capex falling from 2.1x" in r["capital_cycle_evidence"]


def test_signals_that_disagree_read_as_mixed():
    t = _table(
        capex=[-20.0, -20.0, -20.0, -20.0],
        dep=[10.0] * 4,
        rev=[100.0] * 4,
        op=[5.0, 15.0, 15.0, 15.0],
        shares=[1.0] * 4,
    )
    assert read(t)["capital_cycle"] == "mixed"


def test_too_little_history_gives_no_reading_rather_than_a_guess():
    t = _table(capex=[-20.0], dep=[None], rev=[100.0], op=[10.0], shares=[1.0])
    assert read(t) is None


def test_the_plan_metric_reports_the_gap_when_it_cannot_read():
    plan = AnalysisPlan(nodes=[{"id": "c", "metric": "capital_cycle"}])
    node = execute_plan(plan, "T", {"statements": _table([None], [None], [1.0], [1.0], [])})[
        "nodes"
    ][0]
    assert node["status"] == "error" and "capital cycle" in node["error"]
