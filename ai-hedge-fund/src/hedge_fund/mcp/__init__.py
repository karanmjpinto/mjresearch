"""MCP (Model Context Protocol) server surface.

Exposes the hedge fund's capabilities — AI research, market data, SEC filings,
backtesting, and portfolio optimization — as MCP tools so the stack can be
driven from Claude Desktop, Cursor, or any MCP-compatible client.

Run via the `hedge-fund-mcp` script entrypoint (see pyproject.toml).
"""

from hedge_fund.mcp.server import mcp, main

__all__ = ["mcp", "main"]
