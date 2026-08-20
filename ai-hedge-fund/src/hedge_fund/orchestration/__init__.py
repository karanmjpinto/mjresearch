"""Phase 7: Research graph orchestration.

The research flow is a fan-out / fan-in graph:

    ┌───────────────────────────────────────┐
    │   data_snapshot (price, fundamentals, │
    │   technicals, news, sentiment, …)     │
    └───────────────┬───────────────────────┘
                    │
           ┌────────┼────────┐   (fan-out, parallel via asyncio.gather)
           ▼        ▼        ▼
    ┌──────────┐┌──────────┐┌──────────┐ …
    │ Persona 1││ Persona 2││ Persona N│
    │ (Buffett)││ (Graham) ││  (Burry) │
    └────┬─────┘└────┬─────┘└────┬─────┘
         │           │           │        (fan-in)
         └───────────┼───────────┘
                     ▼
          ┌─────────────────────┐
          │  Portfolio Manager  │
          │   synthesis node    │
          └──────────┬──────────┘
                     ▼
                final thesis
                (+ per-persona details, evaluation, usage)

Implementation is in `hedge_fund.agents.research_agent.run_committee_analysis` —
see that function for the concrete fan-out / fan-in code. This module exposes
the graph as a declarative structure so the UI can render it and the MCP server
can describe the workflow.

A second pipeline, `describe_plan_graph`, covers the plan-based route
(`hedge_fund.agents.plan_agent`), where the model selects metrics and narrates
but the harness computes every number. See `docs/architecture.md`.
"""

from hedge_fund.orchestration.graph import (
    GRAPH_EDGES,
    GRAPH_NODES,
    PLAN_GRAPH_EDGES,
    PLAN_GRAPH_NODES,
    describe_plan_graph,
    describe_research_graph,
)

__all__ = [
    "GRAPH_EDGES",
    "GRAPH_NODES",
    "PLAN_GRAPH_EDGES",
    "PLAN_GRAPH_NODES",
    "describe_plan_graph",
    "describe_research_graph",
]
