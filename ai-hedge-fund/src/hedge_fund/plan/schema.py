"""The plan: a typed program the model writes and the harness executes.

A plan is a DAG of nodes, each naming one registered metric and its arguments.
It is not a to-do list in prose — there is nothing left for the model to
reinterpret at execution time, which is precisely what stops a plan from
drifting between runs.

Plans may also carry *clarifications*: methodology choices the model judged
contestable. Each is closed-form with a recommended option, so answering costs a
moment and skipping is always safe. The answer is compiled into the plan before
execution rather than left to be quietly resolved mid-run.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class Clarification(BaseModel):
    """A methodology decision worth surfacing before the numbers are computed."""

    id: str = Field(max_length=64, description="Stable identifier for this question")
    question: str = Field(max_length=500)
    options: list[str] = Field(default_factory=list, max_length=6)
    recommended: str = Field(default="", max_length=200)
    affects: list[str] = Field(
        default_factory=list, description="Node ids whose parameters this choice changes"
    )
    answer: str | None = Field(default=None, description="Chosen option, once answered")

    @property
    def effective(self) -> str:
        """The option in force: the answer if given, otherwise the recommendation."""
        return self.answer or self.recommended

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "options": self.options,
            "recommended": self.recommended,
            "affects": self.affects,
            "answer": self.answer,
            "effective": self.effective,
            "answered": self.answer is not None,
        }


class PlanNode(BaseModel):
    id: str = Field(max_length=64)
    metric: str = Field(max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    why: str = Field(default="", max_length=400, description="Why this metric answers the question")

    @field_validator("id", "metric")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v


class AnalysisPlan(BaseModel):
    question: str = Field(default="", max_length=1000)
    nodes: list[PlanNode] = Field(default_factory=list, max_length=24)
    clarifications: list[Clarification] = Field(default_factory=list, max_length=6)

    def node_ids(self) -> list[str]:
        return [n.id for n in self.nodes]

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "nodes": [n.model_dump() for n in self.nodes],
            "clarifications": [c.as_dict() for c in self.clarifications],
        }


class PlanValidationError(ValueError):
    """The plan is not executable as written."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def topological_order(plan: AnalysisPlan) -> list[PlanNode]:
    """Order nodes so every dependency runs first. Raises on cycles.

    Ties are broken by the order the model wrote them, so execution order — and
    therefore the plan hash — is stable across runs.
    """
    by_id = {n.id: n for n in plan.nodes}
    position = {n.id: i for i, n in enumerate(plan.nodes)}
    remaining = {n.id: {d for d in n.depends_on if d in by_id} for n in plan.nodes}

    ordered: list[PlanNode] = []
    while remaining:
        ready = sorted(
            (nid for nid, deps in remaining.items() if not deps), key=lambda n: position[n]
        )
        if not ready:
            raise PlanValidationError(
                [f"dependency cycle among nodes: {', '.join(sorted(remaining))}"]
            )
        for nid in ready:
            ordered.append(by_id[nid])
            del remaining[nid]
        for deps in remaining.values():
            deps.difference_update(ready)
    return ordered


def validate_plan(plan: AnalysisPlan) -> AnalysisPlan:
    """Static checks before anything executes: ids, metrics, params, and the DAG.

    Every ambiguity resolved here is one that cannot reappear as a wrong number
    later, so validation is deliberately strict — an unknown metric or a bad
    parameter fails the plan rather than being skipped at runtime.
    """
    from hedge_fund.plan.registry import get_metric
    from hedge_fund.plan.types import MetricError

    problems: list[str] = []

    if not plan.nodes:
        problems.append("plan contains no nodes")

    seen: set[str] = set()
    for node in plan.nodes:
        if node.id in seen:
            problems.append(f"duplicate node id: {node.id}")
        seen.add(node.id)

    for node in plan.nodes:
        try:
            metric = get_metric(node.metric)
        except MetricError as e:
            problems.append(f"node '{node.id}': {e}")
            continue
        try:
            metric.coerce_params(node.params)
        except MetricError as e:
            problems.append(f"node '{node.id}': {e}")

        for dep in node.depends_on:
            if dep not in seen and dep not in {n.id for n in plan.nodes}:
                problems.append(f"node '{node.id}' depends on unknown node '{dep}'")
            if dep == node.id:
                problems.append(f"node '{node.id}' depends on itself")

    for clar in plan.clarifications:
        unknown = [a for a in clar.affects if a not in {n.id for n in plan.nodes}]
        if unknown:
            problems.append(
                f"clarification '{clar.id}' affects unknown node(s): {', '.join(unknown)}"
            )
        if clar.answer is not None and clar.options and clar.answer not in clar.options:
            problems.append(
                f"clarification '{clar.id}' answered with an option that was not offered"
            )

    if problems:
        raise PlanValidationError(problems)

    topological_order(plan)  # raises on cycles
    return plan
