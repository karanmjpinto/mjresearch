"""Agent tool module smoke tests."""

from __future__ import annotations

from hedge_fund.agents.tools import AGENT_TOOLS, tool_price_history

# Tools the research layer depends on. Adding a tool should not fail this test;
# removing or renaming one of these should.
REQUIRED_TOOLS = {
    "price_history",
    "fundamentals",
    "technicals",
    "news",
    "research_snapshot",
}


def test_agent_tools_registry_covers_required_tools():
    assert REQUIRED_TOOLS <= set(AGENT_TOOLS.keys())


def test_agent_tools_are_callable():
    for name, fn in AGENT_TOOLS.items():
        assert callable(fn), f"{name} is not callable"


def test_tool_price_history_structure():
    out = tool_price_history("AAPL", days=5)
    assert "ok" in out
    assert out["ticker"] == "AAPL"
    if out["ok"]:
        assert "data" in out
        assert isinstance(out["data"], list)
