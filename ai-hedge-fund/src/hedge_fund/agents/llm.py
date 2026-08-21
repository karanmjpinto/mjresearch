"""LLM invocation with recorded, reproducible parameters.

Every call returns an :class:`LLMResult` carrying the exact model identity, the
sampling parameters used, and a hash of the prompt that produced it. That record
is what makes a run replayable: given the same snapshot, the same prompt hash and
the same params, a differing output is a real finding rather than sampling noise.

Sampling defaults to greedy and seeded. True bit-for-bit determinism is not
something an LLM provider guarantees — batching, quantisation, and hardware all
leak in — so the goal here is narrower and achievable: make the *inputs* fully
pinned and recorded, so any remaining variance is attributable instead of
ambient. The heavier fix, moving numeric work out of the model entirely, lives
in :mod:`hedge_fund.agents.plan`.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from hedge_fund.settings import settings

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """The provider could not be reached — distinct from a bad response."""


class OutputTruncated(RuntimeError):
    """Generation stopped at the token limit, so the JSON is incomplete."""


def prompt_hash(system: str, user: str) -> str:
    """Stable identity for a prompt pair, independent of formatting noise."""
    h = hashlib.sha256()
    h.update(system.encode("utf-8"))
    h.update(b"\x00")
    h.update(user.encode("utf-8"))
    return h.hexdigest()


@dataclass
class LLMResult:
    content: str
    model: str
    params: dict[str, Any]
    usage: dict[str, Any] = field(default_factory=dict)
    prompt_sha256: str = ""
    fingerprint: str | None = None
    latency_ms: int | None = None

    def as_record(self) -> dict[str, Any]:
        """The subset worth persisting on a run."""
        return {
            "model": self.model,
            "params": self.params,
            "usage": self.usage,
            "prompt_sha256": self.prompt_sha256,
            "fingerprint": self.fingerprint,
            "latency_ms": self.latency_ms,
        }


# JSON Schema keywords that Ollama's grammar compiler cannot express cheaply.
# A `maxLength: 12000` becomes a grammar with twelve thousand alternatives; in
# practice the constraint is dropped silently and the model returns unconstrained
# prose — which is worse than not asking for a schema at all. Length and pattern
# limits stay enforced where they belong, in Pydantic validation after parsing.
_GBNF_HOSTILE_KEYS = frozenset(
    {"maxLength", "minLength", "pattern", "maxItems", "minItems", "format", "default"}
)


def gbnf_safe_schema(schema: Any) -> Any:
    """Strip schema keywords that break grammar-constrained decoding."""
    if isinstance(schema, dict):
        return {k: gbnf_safe_schema(v) for k, v in schema.items() if k not in _GBNF_HOSTILE_KEYS}
    if isinstance(schema, list):
        return [gbnf_safe_schema(v) for v in schema]
    return schema


def sampling_params() -> dict[str, Any]:
    """The sampling configuration applied to every research call."""
    params: dict[str, Any] = {
        "temperature": settings.llm_temperature,
        "seed": settings.llm_seed,
        "top_p": settings.llm_top_p,
        "max_output_tokens": settings.llm_max_output_tokens,
    }
    if settings.llm_provider == "ollama":
        params["num_ctx"] = settings.ollama_num_ctx
        params["repeat_penalty"] = settings.ollama_repeat_penalty
        if settings.ollama_think is not None:
            params["think"] = settings.ollama_think
    return params


def default_model() -> str:
    """The model the active provider uses when a call names none."""
    return settings.ollama_model if settings.llm_provider == "ollama" else settings.llm_model


def model_for_role(role: str | None) -> str | None:
    """Model override configured for a pipeline stage, or None to use the default.

    Stages differ in what they are worth. Reading a data bundle into a structured
    opinion is bulk work that a small model does acceptably; reconciling four of
    those opinions is the single call a person reads, and is worth a larger one.
    Returning None rather than the default keeps the override *absent* from the
    request when unconfigured, so the unconfigured path stays byte-identical.
    """
    if role == "persona":
        return settings.llm_persona_model or None
    if role == "synthesis":
        return settings.llm_synthesis_model or None
    return None


async def _ollama_chat(
    system: str, user: str, schema: dict[str, Any] | None = None, *, model: str | None = None
) -> tuple[str, dict[str, Any], str, None]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    name = model or settings.ollama_model
    payload: dict[str, Any] = {
        "model": name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        # A bare "json" format only constrains syntax, so a prompt ending in a
        # large JSON bundle invites the model to echo that bundle back as its
        # answer — observed with qwen3:30b. Passing the schema constrains the
        # shape as well, which makes that failure structurally impossible.
        "format": gbnf_safe_schema(schema) if schema is not None else "json",
        "options": {
            "temperature": settings.llm_temperature,
            "seed": settings.llm_seed,
            "top_p": settings.llm_top_p,
            "num_predict": settings.llm_max_output_tokens,
            "num_ctx": settings.ollama_num_ctx,
            "repeat_penalty": settings.ollama_repeat_penalty,
        },
    }
    if settings.ollama_think is not None:
        payload["think"] = settings.ollama_think

    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
            r = await client.post(url, json=payload)
            # Models without a thinking mode reject the key outright. Drop it and
            # retry rather than failing a request over an unsupported option.
            if r.status_code >= 400 and "think" in payload and "think" in r.text.lower():
                payload.pop("think")
                r = await client.post(url, json=payload)
    except httpx.ConnectError as e:
        raise LLMUnavailable(
            f"Cannot reach Ollama at {settings.ollama_base_url}. "
            "Start the daemon: `ollama serve` (or install from https://ollama.com). "
            f"Ensure the model exists: `ollama pull {name}` then `ollama list`."
        ) from e
    except httpx.TimeoutException as e:
        # str() on an httpx timeout is empty, which surfaces as a blank error.
        # A timeout on a local model is nearly always memory pressure: if the KV
        # cache does not fit, generation falls back to swap and crawls.
        raise LLMUnavailable(
            f"Ollama timed out after {settings.ollama_timeout_s:.0f}s running "
            f"{name} (context {settings.ollama_num_ctx}). "
            "Check `ollama ps` — if SIZE is far larger than the model on disk, the "
            "context window is oversized; lower OLLAMA_NUM_CTX or use a smaller model."
        ) from e
    if r.status_code >= 400:
        raise RuntimeError(f"Ollama HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    msg = data.get("message") or {}
    content = (msg.get("content") or "").strip()

    # Hitting the token ceiling truncates the JSON mid-object, which then
    # surfaces as an opaque parse error. Name the actual cause instead.
    if data.get("done_reason") == "length":
        raise OutputTruncated(
            f"{name} hit the {settings.llm_max_output_tokens}-token "
            "output limit and the JSON is incomplete. Raise LLM_MAX_OUTPUT_TOKENS, "
            "or reduce RESEARCH_MAX_CONTEXT_CHARS so the model writes less."
        )

    usage = {
        "prompt_tokens": data.get("prompt_eval_count"),
        "completion_tokens": data.get("eval_count"),
        "done_reason": data.get("done_reason"),
    }
    return content, usage, f"ollama:{name}", None


async def _openai_chat(
    system: str, user: str, schema: dict[str, Any] | None = None, *, model: str | None = None
) -> tuple[str, dict[str, Any], str, str | None]:
    try:
        from openai import AsyncOpenAI
    except ImportError as e:
        raise RuntimeError(
            "OpenAI provider selected but package not installed. Run: uv sync --extra openai"
        ) from e

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    name = model or settings.llm_model
    resp = await client.chat.completions.create(
        model=name,
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        seed=settings.llm_seed,
        max_tokens=settings.llm_max_output_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    content = (resp.choices[0].message.content or "").strip()
    usage = {
        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else None,
        "completion_tokens": resp.usage.completion_tokens if resp.usage else None,
    }
    return content, usage, f"openai:{name}", getattr(resp, "system_fingerprint", None)


async def call_json(
    system: str,
    user: str,
    schema: dict[str, Any] | None = None,
    *,
    model: str | None = None,
) -> LLMResult:
    """Run one JSON completion, recording everything needed to replay it.

    Pass ``schema`` (a JSON Schema, e.g. from ``Model.model_json_schema()``) to
    constrain the output shape rather than merely its syntax. Strongly preferred:
    it removes a whole class of failure where the model returns well-formed JSON
    that is not the object you asked for.

    ``model`` overrides the active provider's configured model for this one call
    — see :func:`model_for_role`. The resolved name is recorded on the result, so
    a run mixing models stays attributable stage by stage.

    Raises :class:`LLMUnavailable` when the provider is unreachable,
    :class:`OutputTruncated` when generation hit the token ceiling, and
    ``RuntimeError`` for provider-side errors.
    """
    started = time.perf_counter()
    if settings.llm_provider == "ollama":
        content, usage, resolved, fingerprint = await _ollama_chat(
            system, user, schema, model=model
        )
    else:
        content, usage, resolved, fingerprint = await _openai_chat(
            system, user, schema, model=model
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return LLMResult(
        content=content,
        model=resolved,
        params=sampling_params(),
        usage=usage,
        prompt_sha256=prompt_hash(system, user),
        fingerprint=fingerprint,
        latency_ms=elapsed_ms,
    )
