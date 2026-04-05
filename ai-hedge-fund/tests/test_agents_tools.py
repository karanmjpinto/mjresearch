"""Agent tool module smoke tests."""

from __future__ import annotations

from hedge_fund.agents.tools import AGENT_TOOLS, tool_price_history


def test_agent_tools_registry():
    assert set(AGENT_TOOLS.keys()) == {
        "price_history",
        "fundamentals",
        "technicals",
        "news",
        "research_snapshot",
    }


def test_tool_price_history_structure():
    out = tool_price_history("AAPL", days=5)
    assert "ok" in out
    assert out["ticker"] == "AAPL"
    if out["ok"]:
        assert "data" in out
        assert isinstance(out["data"], list)
