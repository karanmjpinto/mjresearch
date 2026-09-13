"""Stage 04 — what you already think, assembled into one view.

The other stages read the market. This one reads you, which is why it is the
only stage whose absence is reported as a state rather than an error: a vault
that says nothing about a name is a real and useful answer, and pretending
otherwise would turn an empty result into false comfort.

Frameworks are resolved from a folder as well as a title list, so a new note
dropped into your investing folder becomes a lens on the next request without
anybody editing configuration.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from hedge_fund.knowledge.match import coverage, match_ticker
from hedge_fund.knowledge.vault import VaultIndex, build_index, vault_root

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "vault.json"

#: How many notes of each kind to return. A lens is something you read, and a
#: hundred-row list is not read — it is scrolled past.
MAX_PER_KIND = 12


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("no usable %s (%s); no framework notes will be marked", CONFIG_PATH, exc)
        return {}


def framework_titles(index: VaultIndex) -> tuple[str, ...]:
    """Note titles that are lenses: named explicitly, or sitting in a lens folder."""
    cfg = _config()
    folders = {f.strip().strip("/").lower() for f in cfg.get("framework_folders", []) if f.strip()}
    titles = {t.strip() for t in cfg.get("framework_titles", []) if t.strip()}

    for note in index.notes:
        top = note.folder.split("/", 1)[0].lower() if note.folder else ""
        if top and top in folders:
            titles.add(note.title)

    return tuple(sorted(titles))


def build_lens(
    ticker: str,
    *,
    name: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
) -> dict[str, Any]:
    """Your own notes on this name, each carrying the rule that surfaced it.

    Returns ``configured: False`` rather than raising when no vault is set up:
    this stage is optional by design, and the rest of the flow must not depend
    on a personal directory existing on the machine serving the request.
    """
    t = ticker.strip().upper()
    if vault_root() is None:
        return {
            "ticker": t,
            "configured": False,
            "finding": (
                "No vault is connected. Set VAULT_PATH to your Obsidian folder and this "
                "stage will show what you have already written about this name."
            ),
            "coverage": coverage([]),
            "company": [],
            "themes": [],
            "frameworks": [],
        }

    index = build_index()
    if index is None or not index.notes:
        return {
            "ticker": t,
            "configured": True,
            "finding": "The vault is connected but empty — nothing to match against.",
            "coverage": coverage([]),
            "company": [],
            "themes": [],
            "frameworks": [],
            "vault": {"notes": 0},
        }

    matches = match_ticker(
        index,
        t,
        name=name,
        sector=sector,
        industry=industry,
        frameworks=framework_titles(index),
    )
    cov = coverage(matches)

    def rows(kind: str) -> list[dict[str, Any]]:
        return [m.as_dict() for m in matches if m.kind == kind][:MAX_PER_KIND]

    return {
        "ticker": t,
        "configured": True,
        "finding": cov["finding"],
        "coverage": cov,
        "company": rows("company"),
        "themes": rows("theme"),
        "frameworks": rows("framework"),
        "vault": {
            "notes": len(index.notes),
            "built_at": index.built_at,
            # The root is deliberately absent: it is a personal path, and the
            # browser has no use for it.
        },
        # Keyed to match the row lists above, so a caller reading `themes`
        # does not have to remember that the count is under `theme`.
        "truncated": {
            plural: max(0, len([m for m in matches if m.kind == kind]) - MAX_PER_KIND)
            for kind, plural in (
                ("company", "company"),
                ("theme", "themes"),
                ("framework", "frameworks"),
            )
        },
    }
