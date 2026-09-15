"""Putting a page back into the vault.

Everything else in `knowledge/` reads. This writes, into somebody's real
Obsidian folder, which is a different kind of operation and is treated as one.

Four rules, each one there because the failure it prevents is unrecoverable:

  1. **Never overwrite.** If a file exists at the target path, this refuses and
     says so. A valuation note is hand-edited after it is generated, and
     silently replacing one destroys work that only existed there.
  2. **Never escape the vault.** The path is resolved and checked to be inside
     the configured root. A ticker arrives from a URL, and `../../.ssh` is a
     ticker as far as string formatting is concerned.
  3. **Preview before write.** `render` produces the markdown and touches
     nothing; `write` is a separate call. The API exposes them as GET and POST
     for the same reason.
  4. **Their template, if they have one.** A note written in this codebase's
     shape would be a foreign object in a vault with its own conventions. If a
     template note exists, its headings are used and the content is slotted
     under them; only when there is none does the built-in shape apply.

The generated note links back to whatever matched, so it lands connected to the
graph rather than as an orphan — which is most of the point of writing it into
a vault instead of exporting a file.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hedge_fund.knowledge.vault import vault_root

logger = logging.getLogger(__name__)

#: Where a generated page goes, relative to the vault root. A folder of its own
#: so a generated note is never mistaken for one that was written by hand.
OUTPUT_FOLDER = "MJ Research"

#: Titles that mark a note as the user's own one-pager template, tried in order.
TEMPLATE_TITLES = (
    "Value One Pager",
    "Value One-Pager",
    "One Pager Template",
    "Company One Pager",
    "Equity One Pager",
)

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
#: Obsidian forbids these in a filename, and a ticker can carry a dot or slash.
_UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]]')


class WriteBackError(RuntimeError):
    """The note was not written, and the caller is told exactly why."""


@dataclass(frozen=True)
class Page:
    """A rendered note, and where it would go."""

    title: str
    relative_path: str
    markdown: str
    template: str | None
    exists: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            # Relative only. The absolute path is personal and the browser has
            # no use for it, same reason `build_lens` omits the root.
            "relative_path": self.relative_path,
            "markdown": self.markdown,
            "template": self.template,
            "exists": self.exists,
        }


def safe_stem(ticker: str, name: str | None = None) -> str:
    """A filename Obsidian will accept, from a symbol that may contain anything."""
    base = f"{ticker.strip().upper()}"
    if name:
        clean = _UNSAFE.sub("", name).strip()
        if clean:
            base = f"{base} — {clean}"
    return _UNSAFE.sub("-", base).strip(" .") or "Untitled"


def _resolve_target(stem: str) -> tuple[Path, str]:
    """Absolute target inside the vault, plus its vault-relative spelling."""
    root = vault_root()
    if root is None:
        raise WriteBackError("No vault is connected. Set VAULT_PATH to your Obsidian folder first.")
    root = root.resolve()
    rel = f"{OUTPUT_FOLDER}/{stem}.md"
    target = (root / rel).resolve()

    # Rule 2. `is_relative_to` on the *resolved* paths, so a symlink or a `..`
    # smuggled through the ticker cannot land a file outside the vault.
    if not target.is_relative_to(root):
        raise WriteBackError("Refused: that would write outside the vault.")
    return target, rel


def find_template(index: Any) -> tuple[str, str] | None:
    """The reader's own one-pager template, as (title, body), if there is one."""
    if index is None or not getattr(index, "notes", None):
        return None
    wanted = {t.lower() for t in TEMPLATE_TITLES}
    for note in index.notes:
        if note.title.strip().lower() in wanted:
            try:
                body = (vault_root() / note.path).read_text(encoding="utf-8", errors="replace")  # type: ignore[operator]
            except (OSError, TypeError) as exc:
                logger.warning("template %s unreadable (%s)", note.path, exc)
                return None
            return note.title, body
    return None


def _slot_into_template(body: str, sections: dict[str, str]) -> str:
    """Fill a template by appending under the headings it already has.

    The template's own structure is preserved exactly — headings, order,
    frontmatter, any prose between them. Content is inserted after the heading
    whose text best matches a section we have, and anything we could not place
    is appended at the end under its own heading rather than dropped.
    """
    placed: set[str] = set()
    out: list[str] = []
    last = 0

    for m in _HEADING.finditer(body):
        heading = m.group(2).strip().lower()
        key = next((k for k in sections if k not in placed and k.lower() in heading), None)
        end = m.end()
        out.append(body[last:end])
        if key:
            out.append(f"\n\n{sections[key]}\n")
            placed.add(key)
        last = end

    out.append(body[last:])
    tail = [f"\n\n## {k}\n\n{v}\n" for k, v in sections.items() if k not in placed]
    return "".join(out) + "".join(tail)


def _default_page(title: str, sections: dict[str, str], links: list[str]) -> str:
    """The shape used when the vault has no template of its own."""
    today = datetime.now(UTC).date().isoformat()
    front = "\n".join(
        [
            "---",
            f'title: "{title}"',
            f"created: {today}",
            "tags:",
            "  - mj-research",
            "  - valuation",
            "---",
            "",
        ]
    )
    parts = [front, f"# {title}", ""]
    for k, v in sections.items():
        parts += [f"## {k}", "", v, ""]
    if links:
        parts += ["## Related notes", ""]
        parts += [f"- [[{link}]]" for link in links]
        parts += [""]
    return "\n".join(parts)


def render(
    ticker: str,
    *,
    name: str | None = None,
    sections: dict[str, str],
    links: list[str] | None = None,
    index: Any = None,
) -> Page:
    """Build the note without writing it. Rule 3."""
    t = ticker.strip().upper()
    if not t:
        raise WriteBackError("No ticker given.")

    stem = safe_stem(t, name)
    target, rel = _resolve_target(stem)

    tpl = find_template(index)
    if tpl:
        tpl_title, tpl_body = tpl
        markdown = _slot_into_template(tpl_body, sections)
        # The template is a template, not this company's note: the reader's own
        # placeholders are left alone rather than half-substituted, except for
        # the title, which is the one thing every template gets wrong when
        # copied by hand.
        markdown = markdown.replace("{{title}}", stem).replace("{{ticker}}", t)
        if links:
            markdown += (
                "\n\n## Related notes\n\n" + "\n".join(f"- [[{link}]]" for link in links) + "\n"
            )
        template_name: str | None = tpl_title
    else:
        markdown = _default_page(stem, sections, links or [])
        template_name = None

    return Page(
        title=stem,
        relative_path=rel,
        markdown=markdown,
        template=template_name,
        exists=target.exists(),
    )


def write(page: Page) -> dict[str, Any]:
    """Write the rendered note. Refuses rather than replacing. Rule 1."""
    target, rel = _resolve_target(page.title)

    if target.exists():
        raise WriteBackError(
            f"{rel} already exists. Rename or move it first — this will not "
            "overwrite a note you may have edited by hand."
        )

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # `x` mode, so two requests racing cannot both believe they created it.
        with target.open("x", encoding="utf-8") as fh:
            fh.write(page.markdown)
    except FileExistsError as exc:
        raise WriteBackError(f"{rel} was created by something else a moment ago.") from exc
    except OSError as exc:
        raise WriteBackError(f"Could not write {rel}: {exc}") from exc

    logger.info("wrote vault note %s (%d bytes)", rel, len(page.markdown))
    return {
        "written": True,
        "relative_path": rel,
        "bytes": len(page.markdown.encode("utf-8")),
        "template": page.template,
    }
