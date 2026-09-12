"""Matching a company to what you have already written about it.

Every match states the rule that produced it. A list of "related notes" with no
reason is unfalsifiable — you cannot tell a real connection from a coincidence
of words — and the whole value of this stage is knowing whether your own
thinking already covers a name.

Three kinds of match, deliberately unequal:

* A **company** note is direct coverage: the ticker or the name appears.
* A **theme** note is context: it is about the sector, industry or a subject the
  company sits inside.
* A **framework** note is a lens. It applies to any company, so it is never
  counted as coverage of this one — it is a tool to point at it.

Conflating the third with the first is what would let a vault full of general
frameworks masquerade as deep knowledge of every ticker in the market.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from hedge_fund.knowledge.vault import Note, VaultIndex

#: Corporate suffixes that stop a name matching a note title.
_SUFFIXES = re.compile(
    r"\b(inc|inc\.|incorporated|corp|corp\.|corporation|plc|ltd|limited|co|co\.|company|"
    r"holdings|group|sa|s\.a\.|nv|n\.v\.|ag|the)\b",
    re.I,
)

#: Words too common to carry a sector match on their own.
_GENERIC = {
    "and",
    "the",
    "other",
    "general",
    "diversified",
    "services",
    "products",
    "basic",
    "materials",
    "building",
    "equipment",
    "industry",
    "industrial",
    "consumer",
    "holding",
    "holdings",
    "systems",
    "solutions",
    "technologies",
    "manufacturing",
    "specialty",
    "misc",
    "miscellaneous",
}

#: A deliberately short list of spellings that differ between American
#: filings and British notes. Anything longer belongs in a synonym file.
_ALIASES = {
    "aluminum": "aluminium",
    "aluminium": "aluminum",
    "defense": "defence",
    "defence": "defense",
}


@dataclass(frozen=True)
class Match:
    kind: str  # company | theme | framework
    title: str
    path: str
    reason: str
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "path": self.path,
            "reason": self.reason,
            "tags": list(self.tags),
        }


def normalise_name(name: str) -> str:
    """A company name reduced to the part someone would actually write down."""
    cleaned = _SUFFIXES.sub(" ", name or "")
    cleaned = re.sub(r"[^\w\s&-]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def theme_terms(sector: str | None, industry: str | None) -> dict[str, list[str]]:
    """The three ways a sector may legitimately match, kept apart.

    A phrase is specific enough to trust anywhere in a note. A single word is
    trusted only as an exact tag, or as a distinctive noun in a title, which is
    what stops "Basic Materials" dragging in every note containing "materials".
    """
    phrases: list[str] = []
    exact_tags: list[str] = []
    nouns: list[str] = []

    for source in (sector, industry):
        cleaned = (source or "").strip().lower()
        if not cleaned:
            continue
        words = [w for w in re.split(r"[^\w]+", cleaned) if w]
        if len(words) > 1:
            phrases.append(" ".join(words))
        for w in words:
            if len(w) < 4 or w in _GENERIC:
                continue
            exact_tags.append(w)
            nouns.append(w)
            alias = _ALIASES.get(w)
            if alias:
                exact_tags.append(alias)
                nouns.append(alias)

    return {
        "phrases": list(dict.fromkeys(phrases)),
        "exact_tags": list(dict.fromkeys(exact_tags)),
        "nouns": list(dict.fromkeys(nouns)),
    }


def _theme_match(note: Note, title_l: str, terms: dict[str, list[str]]) -> str | None:
    """Why this note is about the same subject, or None, which is usually right."""
    for phrase in terms["phrases"]:
        if phrase in title_l:
            return f"the title is about {phrase!r}"
        if phrase in note.haystack:
            return f"the note discusses {phrase!r}"
    for tag in terms["exact_tags"]:
        if tag in note.tags:
            return f"tagged #{tag}"
    for noun in terms["nouns"]:
        if re.search(rf"(?<![a-z]){re.escape(noun)}(?![a-z])", title_l):
            return f"the title names {noun!r}"
    return None


def match_ticker(
    index: VaultIndex,
    ticker: str,
    *,
    name: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    frameworks: tuple[str, ...] = (),
) -> list[Match]:
    """Every note that touches this company, and why it counts as touching it."""
    t = ticker.strip().upper()
    if not t:
        return []

    # `$AAPL` with a word boundary: a bare "AA" would otherwise match any word
    # containing it, and a vault is full of prose.
    cash_tag = re.compile(rf"\${re.escape(t)}\b", re.I)
    bare_in_title = re.compile(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])")
    short_name = normalise_name(name or "")
    terms = theme_terms(sector, industry)
    framework_titles = {f.strip().lower() for f in frameworks if f.strip()}

    out: list[Match] = []
    for note in index.notes:
        title_l = note.title.lower()

        if title_l in framework_titles:
            out.append(
                Match(
                    "framework",
                    note.title,
                    note.path,
                    "a framework you apply to any company",
                    note.tags,
                )
            )
            continue

        if bare_in_title.search(note.title):
            out.append(Match("company", note.title, note.path, f"the title carries {t}", note.tags))
            continue
        if cash_tag.search(note.haystack):
            out.append(
                Match("company", note.title, note.path, f"the note mentions ${t}", note.tags)
            )
            continue
        if short_name and len(short_name) >= 3 and short_name in title_l:
            out.append(
                Match("company", note.title, note.path, f"the title names {short_name}", note.tags)
            )
            continue

        theme = _theme_match(note, title_l, terms)
        if theme:
            out.append(Match("theme", note.title, note.path, theme, note.tags))

    return out


def coverage(matches: list[Match]) -> dict[str, Any]:
    """How much of your own thinking this name actually sits inside.

    Frameworks are excluded on purpose. They apply to everything, so counting
    them would let a vault of general models look like deep knowledge of every
    ticker. Thin coverage is a finding — it says the edge here is not yours yet.
    """
    company = [m for m in matches if m.kind == "company"]
    theme = [m for m in matches if m.kind == "theme"]
    lenses = [m for m in matches if m.kind == "framework"]

    # A company note is worth far more than a theme note, and the curve flattens
    # fast: five theme notes is context, fifty is a busy vault.
    score = min(1.0, 0.6 * min(len(company), 2) / 2 + 0.4 * min(len(theme), 5) / 5)
    if company:
        label = "direct"
    elif theme:
        label = "thematic"
    else:
        label = "none"

    return {
        "score": round(score, 3),
        "label": label,
        "company_notes": len(company),
        "theme_notes": len(theme),
        "frameworks_available": len(lenses),
        "finding": (
            "You have written about this company directly."
            if company
            else "Nothing on this company; only the themes around it."
            if theme
            else "Nothing in your vault touches this name — the edge here is not yours yet."
        ),
    }
