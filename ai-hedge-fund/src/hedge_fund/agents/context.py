"""Field-aware context reduction for the model-facing data bundle.

Slicing a serialised JSON string at a character limit hands the model a
syntactically broken object and no indication of what went missing. The model
cannot tell a truncated bundle from a sparse one, so it silently reasons over
whatever survived the cut.

This module reduces the *structure* instead: it drops the least load-bearing
sections first, in a fixed order, and always emits valid JSON carrying a
``_truncation`` manifest naming what was removed. Reduction is deterministic —
the same snapshot and limit always produce the same bundle — because the bundle
is part of the prompt hash that makes a run reproducible.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

# Applied in order until the bundle fits. Earliest steps cost the least analysis
# value; the model is told about every one of them via the manifest.
MAX_STRING_FIELD_CHARS = 1500
NEWS_CAPS = (10, 5, 3)


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def summarize_provenance(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Reduce provenance to the part that bears on the analysis.

    Which provider answered and when is operator diagnostics, not market data.
    Handing the model that nested detail invites it to copy the structure back
    into its answer — observed in practice as a response that echoed the
    provenance block and then degenerated into a whitespace loop. What the model
    legitimately needs is whether the data is trustworthy, which is a warning
    list and a count.
    """
    prov = snapshot.get("provenance")
    if not isinstance(prov, dict):
        return None
    warnings = prov.get("warnings") or []
    return {
        "data_quality_warnings": warnings,
        "warning_count": len(warnings),
        "note": "Lower confidence_in_data when warnings are present.",
    }


def _collapse_provenance(work: dict[str, Any]) -> str | None:
    """Already summarized before reduction begins; nothing further to drop."""
    return None


def _cap_news(work: dict[str, Any], cap: int) -> str | None:
    news = work.get("news")
    if not isinstance(news, list) or len(news) <= cap:
        return None
    removed = len(news) - cap
    work["news"] = news[:cap]
    return f"news: kept {cap} most recent, dropped {removed}"


def _shorten_long_strings(work: dict[str, Any]) -> str | None:
    """Cap oversized free-text fields anywhere in the bundle."""
    shortened: list[str] = []

    def walk(node: Any, path: str) -> Any:
        if isinstance(node, dict):
            return {k: walk(v, f"{path}.{k}" if path else str(k)) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, f"{path}[{i}]") for i, v in enumerate(node)]
        if isinstance(node, str) and len(node) > MAX_STRING_FIELD_CHARS:
            shortened.append(path)
            return node[:MAX_STRING_FIELD_CHARS] + "…[field truncated]"
        return node

    reduced = walk(work, "")
    if not shortened:
        return None
    work.clear()
    work.update(reduced)
    return f"shortened {len(shortened)} long text field(s)"


def _drop_section(work: dict[str, Any], key: str) -> str | None:
    if key not in work or work[key] in (None, [], {}):
        return None
    work.pop(key)
    return f"dropped section: {key}"


def _reduction_steps() -> list[Any]:
    steps: list[Any] = [_collapse_provenance]
    steps += [lambda w, c=c: _cap_news(w, c) for c in NEWS_CAPS]
    steps.append(_shorten_long_strings)
    # Last resorts, most valuable last: sentiment metadata, then news entirely.
    steps.append(lambda w: _drop_section(w, "news_sentiment"))
    steps.append(lambda w: _drop_section(w, "news"))
    steps.append(lambda w: _drop_section(w, "provenance"))
    return steps


# Fields that must survive every reduction — without them the bundle cannot
# support an analysis at all, and an empty answer is better than a wrong one.
# Ordered most to least essential; the severe path sheds from the right.
ESSENTIAL_KEYS = ("ticker", "price", "fundamentals", "as_of_date")

# Below roughly this many characters not even {"ticker": …} plus a marker fits.
# The floor stays valid JSON; it just cannot also honour the limit.
MIN_USEFUL_LIMIT = 80


def _minimal_bundle(data: dict[str, Any], limit: int) -> dict[str, Any]:
    """Absolute floor: identity and price only, explicitly labelled as such."""
    out: dict[str, Any] = {k: data[k] for k in ESSENTIAL_KEYS if k in data}
    out["_truncation"] = {"truncated": True, "severe": True, "limit_chars": limit}
    return out


def build_bundle(data: dict[str, Any], max_chars: int) -> tuple[str, dict[str, Any]]:
    """Return (json_text, truncation_manifest).

    The text is always parseable JSON, and is within ``max_chars`` for any limit
    at or above :data:`MIN_USEFUL_LIMIT`. The manifest always carries a
    ``truncated`` flag so callers never have to probe for optional keys.
    """
    model_view = dict(data)
    summary = summarize_provenance(data)
    if summary is not None:
        model_view["provenance"] = summary

    raw = dumps(model_view)
    if len(raw) <= max_chars:
        return raw, {"truncated": False}

    work = deepcopy(model_view)
    dropped: list[str] = []

    for step in _reduction_steps():
        note = step(work)
        if note:
            dropped.append(note)
        candidate = dict(work)
        candidate["_truncation"] = {
            "truncated": True,
            "severe": False,
            "limit_chars": max_chars,
            "dropped": list(dropped),
            "note": "Sections listed above were removed to fit the context limit. "
            "Treat them as unavailable, not as absent from the market.",
        }
        text = dumps(candidate)
        if len(text) <= max_chars:
            return text, candidate["_truncation"]

    # Structural reduction was not enough: shed essentials from least to most.
    minimal = _minimal_bundle(model_view, max_chars)
    text = dumps(minimal)
    for key in reversed(ESSENTIAL_KEYS[1:]):
        if len(text) <= max_chars:
            break
        if key in minimal:
            minimal.pop(key)
            text = dumps(minimal)

    if len(text) > max_chars:
        minimal = {
            "ticker": model_view.get("ticker"),
            "_truncation": {"truncated": True, "severe": True, "limit_chars": max_chars},
        }
        text = dumps(minimal)
    return text, minimal["_truncation"]
