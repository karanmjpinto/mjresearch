"""Typed signatures for deterministic metrics.

A metric declares its parameters and — crucially — every field it emits, each
with a semantic description. That description is the natural-language half of the
type signature: it is what lets a model choose the right metric without also
being trusted to compute it. Ambiguity resolved here, at plan time, cannot
resurface as a hallucination at execution time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

DType = Literal["number", "integer", "string", "boolean", "date"]
Tier = Literal["load", "transform", "evaluate"]


class MetricError(Exception):
    """A metric could not compute — reported on the node, never raised to the user."""


@dataclass(frozen=True)
class ParamSpec:
    name: str
    dtype: DType
    description: str
    required: bool = False
    default: Any = None
    choices: tuple[Any, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "type": self.dtype,
            "description": self.description,
            "required": self.required,
        }
        if self.default is not None:
            out["default"] = self.default
        if self.choices:
            out["choices"] = list(self.choices)
        if self.minimum is not None:
            out["minimum"] = self.minimum
        if self.maximum is not None:
            out["maximum"] = self.maximum
        return out

    def coerce(self, value: Any) -> Any:
        """Validate and normalize one argument. Raises :class:`MetricError`."""
        if value is None:
            if self.required:
                raise MetricError(f"missing required parameter '{self.name}'")
            return self.default

        if self.dtype in ("number", "integer"):
            if isinstance(value, bool):
                raise MetricError(f"parameter '{self.name}' expects a number, got a boolean")
            try:
                num = float(value)
            except (TypeError, ValueError) as e:
                raise MetricError(f"parameter '{self.name}' expects a number") from e
            if self.dtype == "integer":
                if num != int(num):
                    raise MetricError(f"parameter '{self.name}' expects a whole number")
                num = int(num)
            if self.minimum is not None and num < self.minimum:
                raise MetricError(f"parameter '{self.name}' must be >= {self.minimum}")
            if self.maximum is not None and num > self.maximum:
                raise MetricError(f"parameter '{self.name}' must be <= {self.maximum}")
            value = num
        elif self.dtype == "boolean":
            if not isinstance(value, bool):
                raise MetricError(f"parameter '{self.name}' expects true or false")
        elif self.dtype in ("string", "date"):
            value = str(value)

        if self.choices and value not in self.choices:
            raise MetricError(
                f"parameter '{self.name}' must be one of {list(self.choices)}, got {value!r}"
            )
        return value


@dataclass(frozen=True)
class FieldSpec:
    """One output column, described the way an analyst would describe it."""

    name: str
    dtype: DType
    description: str
    unit: str = ""

    def as_dict(self) -> dict[str, Any]:
        out = {"name": self.name, "type": self.dtype, "description": self.description}
        if self.unit:
            out["unit"] = self.unit
        return out


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    description: str
    tier: Tier
    outputs: tuple[FieldSpec, ...]
    fn: Callable[..., dict[str, Any]]
    params: tuple[ParamSpec, ...] = ()
    # Node ids this metric consumes, by role. Empty means it reads only the snapshot.
    consumes: tuple[str, ...] = ()
    notes: str = ""

    def signature(self) -> dict[str, Any]:
        """The metric as a model sees it when writing a plan."""
        out: dict[str, Any] = {
            "metric": self.id,
            "label": self.label,
            "tier": self.tier,
            "description": self.description,
            "params": [p.as_dict() for p in self.params],
            "outputs": [f.as_dict() for f in self.outputs],
        }
        if self.consumes:
            out["consumes"] = list(self.consumes)
        if self.notes:
            out["notes"] = self.notes
        return out

    def coerce_params(self, given: dict[str, Any] | None) -> dict[str, Any]:
        given = dict(given or {})
        known = {p.name for p in self.params}
        unknown = sorted(set(given) - known)
        if unknown:
            raise MetricError(f"unknown parameter(s) for {self.id}: {', '.join(unknown)}")
        return {p.name: p.coerce(given.get(p.name)) for p in self.params}

    def validate_output(self, value: Any) -> dict[str, Any]:
        """Ensure a metric returned what its signature promised."""
        if not isinstance(value, dict):
            raise MetricError(f"{self.id} returned {type(value).__name__}, expected a mapping")
        declared = {f.name for f in self.outputs}
        missing = sorted(declared - set(value))
        if missing:
            raise MetricError(f"{self.id} omitted declared field(s): {', '.join(missing)}")
        extra = sorted(set(value) - declared)
        if extra:
            raise MetricError(f"{self.id} returned undeclared field(s): {', '.join(extra)}")
        return value


@dataclass
class NodeResult:
    node_id: str
    metric: str
    status: str  # ok | error | skipped
    values: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    cached: bool = False
    why: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "node_id": self.node_id,
            "metric": self.metric,
            "status": self.status,
            "values": self.values,
            "cached": self.cached,
        }
        if self.error:
            out["error"] = self.error
        if self.why:
            out["why"] = self.why
        return out
