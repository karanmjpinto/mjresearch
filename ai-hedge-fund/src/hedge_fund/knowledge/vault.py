"""Reading an Obsidian vault as a local, private data source.

The vault is the one input here that nobody else has, which makes it the only
part of this system capable of an edge that is not already in the price. It is
also personal, so it stays local: the path comes from the environment rather
than the repository, nothing is uploaded, and the index lives in memory.

Notes are indexed rather than searched on demand. Two thousand files is fast to
walk once and far too slow to grep per request, and an index also lets a match
explain itself — the reason a note came back is computed from indexed fields,
not guessed after the fact.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from hedge_fund.settings import settings

logger = logging.getLogger(__name__)

#: How much of each note is kept for matching. Enough to cover the overview and
#: the first sections, without holding a 2,000-file corpus in memory.
HAYSTACK_CHARS = 4_000

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
_TAG_LINE = re.compile(r"^\s*-\s*(.+?)\s*$", re.M)
_INLINE_TAG = re.compile(r"(?<!\w)#([a-zA-Z][\w-]{1,40})")
_WIKILINK = re.compile(r"\[\[([^\]|#]+)")


def vault_root() -> Path | None:
    """Where the vault lives, from configuration only.

    Deliberately not committed: this repository is public, and a personal
    directory path is not something to publish for the convenience of a default.

    ``os.environ`` is read first so a test can point this somewhere else with
    monkeypatch, and settings second so ``VAULT_PATH`` in a local ``.env`` works
    — that file is loaded by pydantic and never reaches ``os.environ``, which
    would otherwise make the documented way of configuring this silently inert.
    """
    raw = os.environ.get("VAULT_PATH", "").strip() or (settings.vault_path or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


@dataclass(frozen=True)
class Note:
    """One note, reduced to what a match needs to be explainable."""

    path: str
    title: str
    tags: tuple[str, ...]
    links: tuple[str, ...]
    haystack: str
    folder: str


@dataclass
class VaultIndex:
    notes: list[Note] = field(default_factory=list)
    root: str = ""
    built_at: str = ""
    fingerprint: tuple[int, float] = (0, 0.0)

    def titles(self) -> set[str]:
        return {n.title.lower() for n in self.notes}


def _parse_tags(front: str) -> list[str]:
    """Tags from YAML frontmatter, in either of the two shapes people write."""
    out: list[str] = []
    if "tags:" not in front:
        return out
    after = front.split("tags:", 1)[1]
    # Inline form: tags: [a, b] or tags: a, b
    first_line = after.splitlines()[0].strip() if after.strip() else ""
    if first_line:
        out += [t.strip().strip("[]\"'") for t in first_line.split(",") if t.strip().strip("[]\"'")]
    # Block form: a dash list on the following lines, stopping at the next key.
    block: list[str] = []
    for line in after.splitlines()[1:]:
        if line.strip() and not line.startswith((" ", "\t", "-")):
            break
        block.append(line)
    out += [m.group(1).strip().strip("\"'") for m in _TAG_LINE.finditer("\n".join(block))]
    return [t.lower() for t in out if t]


def _fingerprint(root: Path) -> tuple[int, float]:
    """Cheap change detection: how many notes there are and the newest mtime."""
    count = 0
    newest = 0.0
    for p in root.rglob("*.md"):
        if any(part.startswith(".") for part in p.parts):
            continue
        count += 1
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            continue
    return count, newest


_cache: VaultIndex | None = None


def build_index(root: Path | None = None, *, force: bool = False) -> VaultIndex | None:
    """Walk the vault once and keep the result until a file changes.

    Rebuilding on a changed fingerprint rather than on a timer means an edit
    shows up on the next request, and an unchanged vault costs one directory
    walk instead of two thousand file reads.
    """
    global _cache
    base = root or vault_root()
    if base is None:
        return None

    fp = _fingerprint(base)
    if not force and _cache is not None and _cache.root == str(base) and _cache.fingerprint == fp:
        return _cache

    notes: list[Note] = []
    for p in base.rglob("*.md"):
        if any(part.startswith(".") for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")[: HAYSTACK_CHARS * 2]
        except OSError as exc:
            logger.debug("could not read %s: %s", p, exc)
            continue

        tags: list[str] = []
        m = _FRONTMATTER.match(text)
        if m:
            tags += _parse_tags(m.group(1))
            body = text[m.end() :]
        else:
            body = text
        tags += [t.lower() for t in _INLINE_TAG.findall(body[:HAYSTACK_CHARS])]

        rel = p.relative_to(base)
        notes.append(
            Note(
                path=str(rel),
                title=p.stem,
                tags=tuple(dict.fromkeys(tags)),
                links=tuple(dict.fromkeys(_WIKILINK.findall(body[:HAYSTACK_CHARS]))),
                haystack=body[:HAYSTACK_CHARS].lower(),
                folder=str(rel.parent) if str(rel.parent) != "." else "",
            )
        )

    _cache = VaultIndex(
        notes=notes,
        root=str(base),
        built_at=datetime.now(UTC).isoformat(timespec="seconds"),
        fingerprint=fp,
    )
    return _cache
