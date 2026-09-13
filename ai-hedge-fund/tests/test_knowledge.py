"""The vault reader and the matcher.

Every test here builds its own small vault on disk. The real vault is personal
and lives outside the repository, so the only test that touches it is the last
one, which skips itself when VAULT_PATH is unset — that is the normal case in
CI and must never be a failure.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hedge_fund.knowledge import build_index, coverage, match_ticker
from hedge_fund.knowledge import lens as lens_mod
from hedge_fund.knowledge.match import Match, normalise_name, theme_terms
from hedge_fund.knowledge.vault import Note, vault_root
from hedge_fund.settings import settings

FRAMEWORKS = ("7 Powers", "Equity Risk Premiums")

#: Captured at import, before the autouse fixture below clears it, so the one
#: test that wants the real vault can still find it.
REAL_VAULT = os.environ.get("VAULT_PATH", "")


@pytest.fixture(autouse=True)
def no_inherited_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with no vault, whatever the developer's own .env says.

    The path is read from the environment *and* from settings, so a local .env
    would otherwise make these tests pass or fail depending on whose machine
    they run on — which is the opposite of what they are for.
    """
    monkeypatch.delenv("VAULT_PATH", raising=False)
    monkeypatch.setattr(settings, "vault_path", None)


def write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A vault small enough to reason about, shaped like the real one."""
    write(
        tmp_path,
        "Companies/Vulcan Materials - VMC.md",
        "---\ntags:\n  - aggregates\n  - cyclicals\n---\nPricing power in crushed stone.\n",
    )
    write(
        tmp_path,
        "Companies/Alcoa.md",
        "Long $AA on the smelter restart. See [[Aluminium Market Mechanics]].\n",
    )
    write(tmp_path, "Themes/Aluminium Market Mechanics.md", "The LME contango. #aluminium\n")
    write(tmp_path, "Themes/Sorbent Materials.md", "Carbon capture media, unrelated to builders.\n")
    write(tmp_path, "Themes/Basic Oxygen Furnaces.md", "Steel, not aggregates.\n")
    write(tmp_path, "Themes/QXO Deep Dive.md", "A roll-up of building materials distribution.\n")
    write(tmp_path, "Frameworks/7 Powers.md", "Hamilton Helmer's seven.\n")
    write(tmp_path, ".obsidian/workspace.md", "Editor state, not a note.\n")
    return tmp_path


# --- vault.py ----------------------------------------------------------------


def test_index_reads_notes_and_skips_dotfolders(vault: Path) -> None:
    idx = build_index(vault, force=True)
    assert idx is not None
    titles = {n.title for n in idx.notes}
    assert "Alcoa" in titles
    assert "workspace" not in titles, "a dot-folder is Obsidian's own state"
    assert idx.root == str(vault)


def test_index_captures_frontmatter_tags_inline_tags_and_links(vault: Path) -> None:
    idx = build_index(vault, force=True)
    assert idx is not None
    by_title = {n.title: n for n in idx.notes}

    assert "aggregates" in by_title["Vulcan Materials - VMC"].tags
    assert "aluminium" in by_title["Aluminium Market Mechanics"].tags, "inline #tag"
    assert "Aluminium Market Mechanics" in by_title["Alcoa"].links


def test_index_is_cached_until_the_vault_changes(vault: Path) -> None:
    first = build_index(vault, force=True)
    again = build_index(vault)
    assert again is first, "an unchanged vault must not be re-read"

    write(vault, "Themes/New Idea.md", "Something I just thought of.\n")
    third = build_index(vault)
    assert third is not first
    assert third is not None
    assert "New Idea" in {n.title for n in third.notes}


def test_no_vault_path_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAULT_PATH", raising=False)
    assert vault_root() is None
    assert build_index() is None, "no vault configured is a state, not a failure"


def test_vault_root_ignores_a_path_that_is_not_a_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "nope"
    monkeypatch.setenv("VAULT_PATH", str(missing))
    assert vault_root() is None


# --- name and term extraction ------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Apple Inc.", "apple"),
        ("Vulcan Materials Corporation", "vulcan materials"),
        ("The Coca-Cola Company", "coca-cola"),
        ("Rio Tinto Group plc", "rio tinto"),
        ("", ""),
    ],
)
def test_normalise_name_drops_corporate_furniture(raw: str, expected: str) -> None:
    assert normalise_name(raw) == expected


def test_theme_terms_keeps_the_phrase_and_drops_generic_words() -> None:
    terms = theme_terms("Basic Materials", "Building Materials")
    assert "basic materials" in terms["phrases"]
    assert "building materials" in terms["phrases"]
    assert terms["nouns"] == [], "every word here is too generic to stand alone"


def test_theme_terms_carries_spelling_aliases() -> None:
    terms = theme_terms("Basic Materials", "Aluminum")
    assert "aluminum" in terms["nouns"]
    assert "aluminium" in terms["nouns"], "filings say aluminum, the vault says aluminium"


def test_theme_terms_survives_missing_sector() -> None:
    assert theme_terms(None, None) == {"phrases": [], "exact_tags": [], "nouns": []}


# --- match.py ----------------------------------------------------------------


def matches_for(vault: Path, ticker: str, **kw: object) -> list[Match]:
    idx = build_index(vault, force=True)
    assert idx is not None
    return match_ticker(idx, ticker, frameworks=FRAMEWORKS, **kw)  # type: ignore[arg-type]


def test_a_ticker_in_the_title_is_direct_coverage(vault: Path) -> None:
    ms = matches_for(vault, "VMC", name="Vulcan Materials Corporation")
    company = [m for m in ms if m.kind == "company"]
    assert [m.title for m in company] == ["Vulcan Materials - VMC"]
    assert company[0].reason == "the title carries VMC"


def test_a_cashtag_in_the_body_is_direct_coverage(vault: Path) -> None:
    ms = matches_for(vault, "AA", name="Alcoa Corp")
    company = [m for m in ms if m.kind == "company"]
    assert [m.title for m in company] == ["Alcoa"]
    assert company[0].reason == "the note mentions $AA"


def test_a_framework_is_never_coverage_of_a_company(vault: Path) -> None:
    ms = matches_for(vault, "VMC", name="Vulcan Materials")
    lenses = [m for m in ms if m.kind == "framework"]
    assert [m.title for m in lenses] == ["7 Powers"]
    assert coverage(ms)["frameworks_available"] == 1
    # And it does not inflate the score.
    assert coverage([m for m in ms if m.kind == "framework"])["label"] == "none"


def test_a_generic_word_in_a_title_is_not_a_theme_match(vault: Path) -> None:
    """The bug this matcher was rewritten to fix.

    "Sorbent Materials" and "Basic Oxygen Furnaces" share a word with "Basic
    Materials" and nothing else. Matching them produced exactly the
    unfalsifiable related-notes list this module exists to avoid.
    """
    ms = matches_for(
        vault,
        "VMC",
        name="Vulcan Materials",
        sector="Basic Materials",
        industry="Building Materials",
    )
    themes = {m.title for m in ms if m.kind == "theme"}
    assert "Sorbent Materials" not in themes
    assert "Basic Oxygen Furnaces" not in themes


def test_a_phrase_in_the_body_is_a_theme_match(vault: Path) -> None:
    ms = matches_for(
        vault,
        "VMC",
        name="Vulcan Materials",
        sector="Basic Materials",
        industry="Building Materials",
    )
    theme = next(m for m in ms if m.kind == "theme" and m.title == "QXO Deep Dive")
    assert theme.reason == "the note discusses 'building materials'"


def test_an_exact_tag_is_a_theme_match(vault: Path) -> None:
    ms = matches_for(vault, "AA", name="Alcoa Corp", sector="Basic Materials", industry="Aluminum")
    theme = next(m for m in ms if m.title == "Aluminium Market Mechanics")
    assert theme.kind == "theme"
    assert theme.reason in {"tagged #aluminium", "the title names 'aluminium'"}


def test_every_match_states_a_reason(vault: Path) -> None:
    ms = matches_for(
        vault,
        "VMC",
        name="Vulcan Materials",
        sector="Basic Materials",
        industry="Building Materials",
    )
    assert ms, "the fixture should produce something"
    assert all(m.reason.strip() for m in ms)


def test_an_empty_ticker_matches_nothing(vault: Path) -> None:
    assert matches_for(vault, "   ") == []


def test_a_short_ticker_does_not_match_inside_a_word(vault: Path) -> None:
    """A bare "AA" must not match "Aardvark" or "NAAFI"."""
    write(vault, "Themes/Aardvark Logistics.md", "Nothing to do with aluminium.\n")
    ms = matches_for(vault, "AA", name="Alcoa Corp")
    assert "Aardvark Logistics" not in {m.title for m in ms if m.kind == "company"}


# --- coverage ----------------------------------------------------------------


def test_coverage_is_honest_when_the_vault_says_nothing() -> None:
    c = coverage([])
    assert c["label"] == "none"
    assert c["score"] == 0.0
    assert "not yours yet" in c["finding"]


def test_coverage_distinguishes_thematic_from_direct() -> None:
    theme_only = [Match("theme", "T", "T.md", "tagged #x") for _ in range(5)]
    direct = [*theme_only, Match("company", "C", "C.md", "the title carries X")]

    assert coverage(theme_only)["label"] == "thematic"
    assert coverage(direct)["label"] == "direct"
    assert coverage(direct)["score"] > coverage(theme_only)["score"]


def test_coverage_score_is_bounded() -> None:
    many = [Match("company", f"C{i}", f"C{i}.md", "r") for i in range(50)]
    many += [Match("theme", f"T{i}", f"T{i}.md", "r") for i in range(500)]
    assert coverage(many)["score"] == 1.0, "a busy vault is not infinite conviction"


def test_a_theme_note_alone_never_reads_as_direct() -> None:
    c = coverage([Match("theme", "T", "T.md", "tagged #semiconductors")])
    assert c["label"] == "thematic"
    assert c["company_notes"] == 0


# --- the real vault, when there is one ---------------------------------------


@pytest.mark.skipif(not REAL_VAULT, reason="no personal vault configured")
def test_the_real_vault_indexes_and_stays_explainable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAULT_PATH", REAL_VAULT)
    idx = build_index(force=True)
    assert idx is not None and idx.notes, "VAULT_PATH is set but nothing was indexed"

    ms = match_ticker(
        idx,
        "NVDA",
        name="NVIDIA Corporation",
        sector="Technology",
        industry="Semiconductors",
        frameworks=FRAMEWORKS,
    )
    assert all(m.reason for m in ms)
    assert all(m.kind in {"company", "theme", "framework"} for m in ms)


def test_note_is_hashable_so_an_index_can_be_diffed() -> None:
    n = Note(path="a.md", title="A", tags=("x",), links=(), haystack="", folder="")
    assert len({n, n}) == 1


# --- lens.py -----------------------------------------------------------------


@pytest.fixture
def lens_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the lens config at a temporary file and clear its cache."""
    cfg = tmp_path / "vault.json"
    cfg.write_text(
        json.dumps(
            {"framework_folders": ["Frameworks"], "framework_titles": ["Investing Principles"]}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(lens_mod, "CONFIG_PATH", cfg)
    lens_mod._config.cache_clear()
    return cfg


def test_framework_folder_makes_a_note_a_lens(vault: Path, lens_config: Path) -> None:
    idx = build_index(vault, force=True)
    assert idx is not None
    titles = lens_mod.framework_titles(idx)
    assert "7 Powers" in titles, "it sits in the Frameworks folder"
    assert "Investing Principles" in titles, "named explicitly, even though absent"
    assert "Alcoa" not in titles


def test_a_missing_config_is_a_warning_not_a_crash(
    vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lens_mod, "CONFIG_PATH", tmp_path / "absent.json")
    lens_mod._config.cache_clear()
    idx = build_index(vault, force=True)
    assert idx is not None
    assert lens_mod.framework_titles(idx) == ()


def test_lens_without_a_vault_says_so_instead_of_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VAULT_PATH", raising=False)
    out = lens_mod.build_lens("AAPL")
    assert out["configured"] is False
    assert out["coverage"]["label"] == "none"
    assert "VAULT_PATH" in out["finding"]
    assert out["company"] == [] and out["themes"] == [] and out["frameworks"] == []


def test_lens_reports_coverage_and_never_leaks_the_vault_path(
    vault: Path, lens_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VAULT_PATH", str(vault))
    out = lens_mod.build_lens(
        "VMC",
        name="Vulcan Materials Corporation",
        sector="Basic Materials",
        industry="Building Materials",
    )

    assert out["configured"] is True
    assert out["coverage"]["label"] == "direct"
    assert [r["title"] for r in out["company"]] == ["Vulcan Materials - VMC"]
    assert str(vault) not in json.dumps(out), "a personal path has no business in a response"


def test_lens_truncates_and_reports_how_much_it_hid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "big"
    for i in range(lens_mod.MAX_PER_KIND + 5):
        write(root, f"Themes/Aluminium Note {i}.md", "#aluminium\n")
    monkeypatch.setenv("VAULT_PATH", str(root))
    monkeypatch.setattr(lens_mod, "CONFIG_PATH", tmp_path / "absent.json")
    lens_mod._config.cache_clear()

    out = lens_mod.build_lens("AA", name="Alcoa Corp", industry="Aluminum")
    assert len(out["themes"]) == lens_mod.MAX_PER_KIND
    assert out["truncated"]["themes"] == 5
