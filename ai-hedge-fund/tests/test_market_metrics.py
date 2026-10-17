"""Macro sensitivity, event studies and peer comparison, on synthetic data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hedge_fund.plan import AnalysisPlan, execute_plan

DAYS = pd.bdate_range("2021-01-01", periods=1300)


class FakeDS:
    """A stock that moves exactly 2% for every 10% move in gas, plus noise."""

    def __init__(self, shock_week: int | None = None) -> None:
        rng = np.random.default_rng(1)
        gas_ret = rng.normal(0, 0.03, len(DAYS))
        if shock_week is not None:
            gas_ret[shock_week] = 0.5
        self.gas = pd.Series(3 * np.exp(np.cumsum(gas_ret)), index=DAYS)
        stock_ret = 0.2 * gas_ret + rng.normal(0, 0.002, len(DAYS))
        self.px = pd.Series(100 * np.exp(np.cumsum(stock_ret)), index=DAYS)

    def get_price_history(self, ticker, days=365, end_date=None):
        return pd.DataFrame({"close": self.px}).tail(int(days * 252 / 365))

    def get_macro_data(self, series_id, days=1825):
        return pd.DataFrame({series_id: self.gas})

    def get_peers(self, ticker):
        return {
            "metrics": {
                "TAP": {"pe_ratio": 10.0},
                "TAP-A": {"pe_ratio": 10.0},
                "SAM": {"pe_ratio": 20.0},
                "BUD": {"pe_ratio": 30.0},
            }
        }

    def get_fundamentals(self, ticker):
        return {
            "AAPL": {"pe_ratio": 40.0},
            "MSFT": {"pe_ratio": 30.0},
            "GOOGL": {"pe_ratio": 20.0},
        }[ticker]


def _node(metric, params, ticker="EXE", ds=None):
    plan = AnalysisPlan(nodes=[{"id": "n", "metric": metric, "params": params}])
    return execute_plan(plan, ticker, {}, data_service=ds or FakeDS())["nodes"][0]


def test_a_known_sensitivity_is_recovered():
    v = _node("macro_sensitivity", {"factor": "natural_gas"})["values"]
    # 0.2 of the daily move, so ~2% per 10% of gas, compounding aside.
    assert v["factor_beta_pct"] == pytest.approx(2.0, abs=0.2)
    assert v["factor_r_squared"] > 0.8 and v["factor_move_unit"] == "a ten percent move"


def test_an_unknown_factor_is_rejected_before_anything_runs():
    from hedge_fund.plan import PlanValidationError

    with pytest.raises(PlanValidationError):
        _node("macro_sensitivity", {"factor": "gold"})


def test_the_event_study_measures_the_week_after_the_shock_not_the_shock_week():
    v = _node("event_study", {"factor": "natural_gas", "sigma": 3.0}, ds=FakeDS(shock_week=600))[
        "values"
    ]
    assert v["shock_weeks_up"] >= 1 and v["event_weeks_used"] > 200


def test_peers_exclude_the_companys_own_other_share_class():
    v = _node("peer_comparison", {}, ticker="TAP")["values"]
    assert v["peers_compared"] == "BUD, SAM"
    assert v["peer_median_pe"] == 25.0 and v["pe_vs_peer_median_pct"] == -60.0


def test_named_peers_are_compared_against_their_median():
    v = _node("peer_comparison", {"peers": "MSFT, GOOGL"}, ticker="AAPL")["values"]
    assert v["peer_median_pe"] == 25.0 and v["pe_vs_peer_median_pct"] == 60.0
