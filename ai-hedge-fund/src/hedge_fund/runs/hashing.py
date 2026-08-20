"""Content addressing for snapshots and runs.

A snapshot hash identifies the *data* an analysis saw. A run key identifies the
whole determined input set — data, prompt, model, sampling parameters — so two
runs sharing a run key should produce the same output. When they do not, the
difference is a real property of the system rather than noise, and that is the
only footing from which research quality can be regression-tested.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Excluded from the snapshot hash: these describe *how* the data was obtained,
# not what it says. Timestamps and cache ages change on every fetch, so leaving
# them in would make every snapshot unique and defeat content addressing.
_NON_CONTENT_KEYS = frozenset({"provenance"})


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, fixed separators, no ASCII escaping."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _content_only(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in snapshot.items() if k not in _NON_CONTENT_KEYS}


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    """Hash the market data in a snapshot, ignoring fetch metadata."""
    return hashlib.sha256(canonical_json(_content_only(snapshot)).encode("utf-8")).hexdigest()


def run_key(
    *,
    snapshot_sha256: str,
    prompt_sha256: str,
    model: str,
    params: dict[str, Any] | None = None,
    mode: str = "single",
) -> str:
    """Identity of a fully determined run input set."""
    payload = canonical_json(
        {
            "snapshot": snapshot_sha256,
            "prompt": prompt_sha256,
            "model": model,
            "params": params or {},
            "mode": mode,
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
