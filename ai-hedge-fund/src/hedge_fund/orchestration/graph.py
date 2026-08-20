"""Declarative description of the research graph — usable by the UI and MCP."""

from __future__ import annotations

from typing import Any

from hedge_fund.agents.personas import (
    DEFAULT_COMMITTEE_PERSONAS,
    get_persona_system_prompt,
    list_persona_ids,
)


def _humanize(persona_id: str) -> str:
    """Convert 'warren_buffett' → 'Warren Buffett'."""
    return " ".join(w.capitalize() for w in persona_id.split("_"))


# Static node/edge topology. Node IDs match execution stages in
# hedge_fund.agents.research_agent.run_committee_analysis.
GRAPH_NODES: list[dict[str, Any]] = [
    {
        "id": "data_snapshot",
        "kind": "data",
        "label": "Market data snapshot",
        "description": (
            "Price window, fundamentals, technicals, news, FinBERT sentiment, "
            "and optional alt-data fetched via the multi-provider data layer."
        ),
    },
    {
        "id": "personas_fanout",
        "kind": "fanout",
        "label": "Committee (parallel)",
        "description": (
            "Each persona runs concurrently (asyncio.gather). Each call is an "
            "independent LLM analysis conditioned on the investor's style prompt."
        ),
    },
    {
        "id": "pm_synthesis",
        "kind": "reduce",
        "label": "Portfolio Manager synthesis",
        "description": (
            "Receives all per-persona JSON outputs, reconciles disagreement, and "
            "emits a single thesis + conviction + bull/bear/risks."
        ),
    },
    {
        "id": "final_thesis",
        "kind": "output",
        "label": "Committee thesis",
        "description": "Structured AiAnalysisBlock returned to the UI and MCP clients.",
    },
]

GRAPH_EDGES: list[dict[str, str]] = [
    {"source": "data_snapshot", "target": "personas_fanout"},
    {"source": "personas_fanout", "target": "pm_synthesis"},
    {"source": "pm_synthesis", "target": "final_thesis"},
]


def describe_research_graph(persona_ids: list[str] | None = None) -> dict[str, Any]:
    """Return a JSON-serializable description of the research graph.

    If `persona_ids` is provided, the fan-out stage is expanded so each
    persona is shown as its own node (useful for UI visualization).
    """
    ids = persona_ids or list(DEFAULT_COMMITTEE_PERSONAS)
    persona_nodes: list[dict[str, Any]] = []
    persona_edges: list[dict[str, str]] = []

    for pid in ids:
        node_id = f"persona:{pid}"
        try:
            prompt = get_persona_system_prompt(pid)
        except ValueError:
            prompt = ""
        # Take first line of the persona preamble as the short description
        first_line = prompt.split("\n", 1)[0].strip() if prompt else ""
        short = first_line[:140] + "…" if len(first_line) > 140 else first_line
        persona_nodes.append(
            {
                "id": node_id,
                "kind": "persona",
                "label": _humanize(pid),
                "description": short,
                "persona_id": pid,
            }
        )
        persona_edges.append({"source": "data_snapshot", "target": node_id})
        persona_edges.append({"source": node_id, "target": "pm_synthesis"})

    # When expanded we drop the collapsed "personas_fanout" node
    nodes = [n for n in GRAPH_NODES if n["id"] != "personas_fanout"] + persona_nodes
    edges = [
        e
        for e in GRAPH_EDGES
        if e["source"] != "personas_fanout" and e["target"] != "personas_fanout"
    ] + persona_edges

    return {
        "nodes": nodes,
        "edges": edges,
        "persona_pool": [{"id": pid, "display_name": _humanize(pid)} for pid in list_persona_ids()],
        "default_committee": list(DEFAULT_COMMITTEE_PERSONAS),
        "execution_model": "parallel_fanout_then_reduce",
    }


# Plan-based pipeline. The model appears twice, in two narrow roles, and never
# produces a number: the planner sees no values, the executor is ordinary Python,
# and the narrator may only cite what the executor computed.
PLAN_GRAPH_NODES: list[dict[str, Any]] = [
    {
        "id": "snapshot",
        "kind": "data",
        "label": "Immutable snapshot",
        "description": (
            "Market data fetched once and content-addressed. Carries provenance: "
            "which provider answered each slot and how its shape verified."
        ),
    },
    {
        "id": "planner",
        "kind": "llm",
        "label": "Planner (LLM)",
        "description": (
            "Chooses deterministic metrics from a fixed catalog and writes a typed "
            "DAG. Sees no market values, so it cannot reason from an invented one."
        ),
    },
    {
        "id": "clarify",
        "kind": "decision",
        "label": "Methodology clarifications",
        "description": (
            "Closed-form questions with a recommended default, raised before "
            "execution. The answer is compiled into the plan rather than left to "
            "be resolved silently mid-run."
        ),
    },
    {
        "id": "executor",
        "kind": "compute",
        "label": "Deterministic executor",
        "description": (
            "Runs each node in topological order in plain Python. Values are "
            "content-addressed, so editing one node does not re-run the others."
        ),
    },
    {
        "id": "narrator",
        "kind": "llm",
        "label": "Narrator (LLM)",
        "description": (
            "Writes the thesis over computed values only, under an explicit no-arithmetic rule."
        ),
    },
    {
        "id": "harness",
        "kind": "verify",
        "label": "Harness checks",
        "description": (
            "Schema validation, heuristic evaluation, and numeric claim "
            "verification against the snapshot. A computed conviction score "
            "replaces the model's, and the substitution is recorded."
        ),
    },
    {
        "id": "run_record",
        "kind": "output",
        "label": "Recorded run",
        "description": (
            "Snapshot hash, plan hash, prompts, model parameters, and output "
            "persisted together so the run can be replayed and diffed."
        ),
    },
]

PLAN_GRAPH_EDGES: list[dict[str, str]] = [
    {"source": "snapshot", "target": "planner"},
    {"source": "planner", "target": "clarify"},
    {"source": "clarify", "target": "executor"},
    {"source": "snapshot", "target": "executor"},
    {"source": "executor", "target": "narrator"},
    {"source": "narrator", "target": "harness"},
    {"source": "executor", "target": "harness"},
    {"source": "harness", "target": "run_record"},
]


def describe_plan_graph() -> dict[str, Any]:
    """Describe the plan-based research pipeline for UI visualization."""
    from hedge_fund.plan import catalog

    specs = catalog()
    return {
        "nodes": PLAN_GRAPH_NODES,
        "edges": PLAN_GRAPH_EDGES,
        "execution_model": "compile_then_execute",
        "metric_count": len(specs),
        "metric_tiers": sorted({s["tier"] for s in specs}),
        "determinism": {
            "numbers_produced_by": "registered Python metrics",
            "model_role": "metric selection and narration only",
            "value_caching": "content-addressed by snapshot, metric, and parameters",
        },
    }
