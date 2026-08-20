"""Execute a validated plan deterministically.

Node values are content-addressed by (snapshot, metric, parameters), so editing
one node does not re-run the others. That is what makes the correction loop cheap
enough to run repeatedly, which is in turn what makes self-correction worth
having at all.

A failing node degrades the plan, it does not abort it: the node is marked with
its error, dependants are skipped, and everything independent still computes. A
partial result with an explicit gap is more useful than no result, and far more
honest than a gap that has been silently filled in.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import pandas as pd

from hedge_fund.plan.registry import get_metric
from hedge_fund.plan.schema import AnalysisPlan, topological_order, validate_plan
from hedge_fund.plan.types import MetricError, NodeResult
from hedge_fund.runs.hashing import canonical_json, snapshot_hash

logger = logging.getLogger(__name__)


class PlanContext:
    """Everything a metric may read: the frozen snapshot, price history, prior facts."""

    def __init__(
        self,
        ticker: str,
        snapshot: dict[str, Any],
        *,
        data_service: Any = None,
        end_date: Any = None,
    ) -> None:
        self.ticker = ticker.upper()
        self.snapshot = snapshot
        self._ds = data_service
        self._end_date = end_date
        self._frames: dict[int, pd.DataFrame] = {}
        # Flat view of every value computed so far, for metrics that combine them.
        self.facts: dict[str, Any] = {}

    def price_frame(self, days: int) -> pd.DataFrame:
        """OHLCV history, fetched once per window and reused across nodes."""
        days = int(days)
        if days in self._frames:
            return self._frames[days]
        if self._ds is None:
            raise MetricError("no data service available to load price history")
        try:
            df = self._ds.get_price_history(self.ticker, days=days, end_date=self._end_date)
        except Exception as e:
            raise MetricError(f"price history fetch failed: {e}") from e
        self._frames[days] = df
        return df

    def absorb(self, values: dict[str, Any]) -> None:
        """Merge a node's outputs into the flat fact table.

        First writer wins: an earlier node's reading of a shared field name is not
        silently overwritten by a later one.
        """
        for key, value in values.items():
            self.facts.setdefault(key, value)


def _node_cache_key(snapshot_digest: str, metric_id: str, params: dict[str, Any]) -> str:
    payload = canonical_json({"snapshot": snapshot_digest, "metric": metric_id, "params": params})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def plan_hash(plan: AnalysisPlan) -> str:
    """Identity of a plan's executable content, ignoring prose fields.

    Two plans with the same hash compute the same values. They do not
    necessarily produce the same *prompt*: each node's ``why`` is passed to the
    narrator and is excluded here. So a matching plan hash answers "was the same
    computation run?", while the run's ``prompt_sha256`` answers "was the same
    question asked?". Replay via ``plan_override`` to hold both fixed.
    """
    payload = canonical_json(
        [
            {"id": n.id, "metric": n.metric, "params": n.params, "depends_on": sorted(n.depends_on)}
            for n in topological_order(plan)
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def execute_plan(
    plan: AnalysisPlan,
    ticker: str,
    snapshot: dict[str, Any],
    *,
    data_service: Any = None,
    end_date: Any = None,
    value_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run every node, returning results, the flat fact table, and diagnostics."""
    validate_plan(plan)
    started = time.perf_counter()

    ctx = PlanContext(ticker, snapshot, data_service=data_service, end_date=end_date)
    digest = snapshot_hash(snapshot)
    cache = value_cache if value_cache is not None else {}

    results: list[NodeResult] = []
    failed: set[str] = set()

    for node in topological_order(plan):
        metric = get_metric(node.metric)

        blocked = [d for d in node.depends_on if d in failed]
        if blocked:
            results.append(
                NodeResult(
                    node_id=node.id,
                    metric=node.metric,
                    status="skipped",
                    error=f"depends on failed node(s): {', '.join(blocked)}",
                    why=node.why or None,
                )
            )
            failed.add(node.id)
            continue

        try:
            params = metric.coerce_params(node.params)
            # Metrics that read prior facts are not addressable by their own
            # parameters alone, so they are always recomputed.
            addressable = not metric.consumes
            key = _node_cache_key(digest, metric.id, params) if addressable else None
            cached = cache.get(key) if addressable else None

            if cached is not None:
                values, was_cached = cached, True
            else:
                values = metric.validate_output(metric.fn(ctx, **params))
                if addressable:
                    cache[key] = values
                was_cached = False

            ctx.absorb(values)
            results.append(
                NodeResult(
                    node_id=node.id,
                    metric=node.metric,
                    status="ok",
                    values=values,
                    cached=was_cached,
                    why=node.why or None,
                )
            )
        except MetricError as e:
            results.append(
                NodeResult(
                    node_id=node.id,
                    metric=node.metric,
                    status="error",
                    error=str(e),
                    why=node.why or None,
                )
            )
            failed.add(node.id)
        except Exception as e:  # a metric bug must not take the request down
            logger.exception("Metric %s raised while executing node %s", node.metric, node.id)
            results.append(
                NodeResult(
                    node_id=node.id,
                    metric=node.metric,
                    status="error",
                    error=f"internal error in {node.metric}: {e}",
                    why=node.why or None,
                )
            )
            failed.add(node.id)

    ok = [r for r in results if r.status == "ok"]
    return {
        "plan_hash": plan_hash(plan),
        "snapshot_sha256": digest,
        "question": plan.question,
        "nodes": [r.as_dict() for r in results],
        "facts": ctx.facts,
        "clarifications": [c.as_dict() for c in plan.clarifications],
        "node_count": len(results),
        "ok_count": len(ok),
        "error_count": sum(1 for r in results if r.status == "error"),
        "skipped_count": sum(1 for r in results if r.status == "skipped"),
        "cache_hits": sum(1 for r in ok if r.cached),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


def render_facts_for_prompt(execution: dict[str, Any]) -> str:
    """Format computed results for the narrative model.

    Each line is a value the harness computed. The model is told to write from
    these and nothing else, which is what keeps invented numbers out of the prose.
    """
    lines: list[str] = []
    for node in execution["nodes"]:
        if node["status"] != "ok":
            lines.append(
                f"- {node['node_id']} ({node['metric']}): NOT AVAILABLE — {node.get('error')}"
            )
            continue
        rendered = ", ".join(f"{k}={v}" for k, v in node["values"].items() if v is not None)
        why = f"  [{node['why']}]" if node.get("why") else ""
        lines.append(f"- {node['node_id']} ({node['metric']}): {rendered}{why}")

    answered = [
        f"- {c['question']} → {c['effective']}"
        + ("" if c["answered"] else " (default, not confirmed by the user)")
        for c in execution.get("clarifications", [])
        if c["effective"]
    ]
    if answered:
        lines.append("")
        lines.append("Methodology decisions in force:")
        lines.extend(answered)
    return "\n".join(lines)
