"""Research synthesis — Ollama (default, local/free) or optional OpenAI."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from hedge_fund.agents.evaluation import evaluate_research
from hedge_fund.agents.guardrails import (
    GuardrailError,
    parse_json_output,
    sanitize_ticker,
    truncate_context,
    validate_output,
)
from hedge_fund.agents.personas import (
    SYNTHESIS_SYSTEM,
    build_pm_synthesis_user_prompt,
    get_persona_system_prompt,
)
from hedge_fund.agents.prompts import RESEARCH_SYSTEM, build_user_prompt
from hedge_fund.settings import settings

logger = logging.getLogger(__name__)


async def _ollama_chat(user_msg: str, *, system: str) -> tuple[str, dict[str, Any]]:
    """Call Ollama /api/chat with JSON mode. Returns (content, usage-ish dict)."""
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.35,
            "num_predict": settings.llm_max_output_tokens,
        },
    }
    async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
        r = await client.post(url, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"Ollama HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    msg = data.get("message") or {}
    content = (msg.get("content") or "").strip()
    usage = {
        "prompt_tokens": data.get("prompt_eval_count"),
        "completion_tokens": data.get("eval_count"),
    }
    return content, usage


async def _openai_chat(user_msg: str, *, system: str) -> tuple[str, dict[str, Any]]:
    try:
        from openai import AsyncOpenAI
    except ImportError as e:
        raise RuntimeError(
            "OpenAI provider selected but package not installed. Run: uv sync --extra openai"
        ) from e

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=0.35,
        max_tokens=settings.llm_max_output_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )
    content = (resp.choices[0].message.content or "").strip()
    usage = {
        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else None,
        "completion_tokens": resp.usage.completion_tokens if resp.usage else None,
    }
    return content, usage


async def _llm_json(user_msg: str, *, system: str) -> tuple[str, dict[str, Any], str]:
    if settings.llm_provider == "ollama":
        content, usage = await _ollama_chat(user_msg, system=system)
        model_label = f"ollama:{settings.ollama_model}"
    else:
        content, usage = await _openai_chat(user_msg, system=system)
        model_label = f"openai:{settings.llm_model}"
    return content, usage, model_label


async def run_research_analysis(
    ticker: str,
    data_snapshot: dict[str, Any],
    *,
    persona_id: str | None = None,
) -> dict[str, Any]:
    """Returns structured analysis + evaluation metadata, or error dict.

    If persona_id is set, use that investor-style system prompt (see agents.personas).
    """
    try:
        sanitize_ticker(ticker)
    except GuardrailError as e:
        return {"error": "guardrail", "message": str(e)}

    system = RESEARCH_SYSTEM
    if persona_id:
        try:
            system = get_persona_system_prompt(persona_id)
        except ValueError as e:
            return {"error": "invalid_persona", "message": str(e)}

    bundle = truncate_context(data_snapshot)
    user_msg = build_user_prompt(ticker.upper(), bundle)

    try:
        content, usage, model_label = await _llm_json(user_msg, system=system)
    except httpx.ConnectError:
        logger.exception("LLM connection failed")
        return {
            "error": "llm_error",
            "message": (
                f"Cannot reach Ollama at {settings.ollama_base_url}. "
                "Start the daemon: `ollama serve` (or install from https://ollama.com). "
                f"Ensure the model exists: `ollama pull {settings.ollama_model}` then `ollama list`."
            ),
        }
    except Exception as e:
        logger.exception("LLM call failed")
        return {"error": "llm_error", "message": str(e)}

    if not content:
        return {"error": "empty_response", "message": "Model returned no content"}

    try:
        parsed = parse_json_output(content)
    except GuardrailError as e:
        return {"error": "parse", "message": str(e)}

    ev = evaluate_research(parsed, data_snapshot=data_snapshot)
    ev["guardrail_warnings"] = validate_output(parsed)
    out: dict[str, Any] = {
        "analysis": parsed.model_dump(),
        "evaluation": ev,
        "model": model_label,
        "usage": usage,
    }
    if persona_id:
        out["persona_id"] = persona_id.strip().lower()
    return out


async def run_pm_synthesis(
    ticker: str,
    data_snapshot: dict[str, Any],
    persona_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Combine persona analyses into one ResearchAnalysisOutput-shaped result."""
    bundle = truncate_context(data_snapshot)
    persona_json = json.dumps(persona_results, ensure_ascii=False, default=str)
    user_msg = build_pm_synthesis_user_prompt(ticker.upper(), persona_json) + (
        f"\n\nOriginal market data bundle (may be truncated):\n{bundle}"
    )

    try:
        content, usage, model_label = await _llm_json(user_msg, system=SYNTHESIS_SYSTEM)
    except httpx.ConnectError:
        logger.exception("LLM connection failed")
        return {
            "error": "llm_error",
            "message": (
                f"Cannot reach Ollama at {settings.ollama_base_url}. "
                f"Start the daemon or check `ollama pull {settings.ollama_model}`."
            ),
        }
    except Exception as e:
        logger.exception("LLM synthesis failed")
        return {"error": "llm_error", "message": str(e)}

    if not content:
        return {"error": "empty_response", "message": "Model returned no content"}

    try:
        parsed = parse_json_output(content)
    except GuardrailError as e:
        return {"error": "parse", "message": str(e)}

    ev = evaluate_research(parsed, data_snapshot=data_snapshot)
    ev["guardrail_warnings"] = validate_output(parsed)
    return {
        "analysis": parsed.model_dump(),
        "evaluation": ev,
        "model": model_label,
        "usage": usage,
    }


async def run_committee_analysis(
    ticker: str,
    data_snapshot: dict[str, Any],
    persona_ids: list[str],
) -> dict[str, Any]:
    """Run each persona, then portfolio-manager synthesis. Returns combined payload or error."""
    if not persona_ids:
        return {"error": "invalid_committee", "message": "committee_personas is empty"}

    committee: list[dict[str, Any]] = []
    usages: list[dict[str, Any]] = []

    for pid in persona_ids:
        one = await run_research_analysis(ticker, data_snapshot, persona_id=pid)
        if "error" in one:
            committee.append({"persona_id": pid, "error": one})
        else:
            committee.append(
                {
                    "persona_id": pid,
                    "analysis": one.get("analysis"),
                    "evaluation": one.get("evaluation"),
                    "model": one.get("model"),
                    "usage": one.get("usage"),
                }
            )
            if one.get("usage"):
                usages.append(one["usage"])

    successes = [c for c in committee if "analysis" in c]
    if not successes:
        return {
            "error": "committee_failed",
            "message": "All persona runs failed",
            "committee": committee,
        }

    synth_input = [
        {"persona_id": c["persona_id"], "analysis": c.get("analysis")}
        for c in successes
    ]
    synth = await run_pm_synthesis(ticker, data_snapshot, synth_input)

    out: dict[str, Any] = {
        "committee": committee,
        "synthesis": synth,
    }
    if "error" not in synth and synth.get("usage"):
        usages.append(synth["usage"])
    out["usage_total"] = usages
    return out
