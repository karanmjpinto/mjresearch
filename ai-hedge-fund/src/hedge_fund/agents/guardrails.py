"""Input sanitization and output validation."""

from __future__ import annotations

import json
import re
from typing import Any

from hedge_fund.agents.schemas import ResearchAnalysisOutput
from hedge_fund.settings import settings


class GuardrailError(Exception):
    pass


_TICKER_OK = re.compile(r"^[A-Z0-9.\-\=]{1,32}$")


def sanitize_ticker(ticker: str) -> str:
    t = ticker.strip().upper()
    if not _TICKER_OK.match(t):
        raise GuardrailError("invalid ticker format")
    return t


def truncate_context(data: dict[str, Any], max_chars: int | None = None) -> str:
    max_chars = max_chars or settings.research_max_context_chars
    raw = json.dumps(data, default=str, ensure_ascii=False)
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 20] + "\n…[truncated]"


def parse_json_output(text: str) -> ResearchAnalysisOutput:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise GuardrailError(f"invalid JSON from model: {e}") from e
    return ResearchAnalysisOutput.model_validate(obj)


def validate_output(output: ResearchAnalysisOutput) -> list[str]:
    """Return warnings (non-fatal)."""
    warnings: list[str] = []
    if len(output.investment_thesis) < 80:
        warnings.append("thesis unusually short")
    if output.stance not in ("BUY", "HOLD", "SELL", "WATCH"):
        warnings.append("stance not in expected set")
    return warnings
