"""The constraint chain, the curated map, and what the vault proposes.

The behaviour worth protecting here is the refusals. A constraint map is easy
to make look authoritative and hard to make honest, so most of these tests
assert that something is *not* claimed: a stale number does not count as
current, a blank is not a zero, and a subject pulled out of someone's notes
never receives a score.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from hedge_fund.constraints import (
    ConstraintError,
    Measurement,
    Route,
    binding_leg,
    capture_leg,
    derive_candidates,
    durability_leg,
    validate,
)
from hedge_fund.constraints import catalogue as cat
from hedge_fund.constraints.derive import MIN_FLAGGED_RATIO, MIN_NOTES
from hedge_fund.knowledge.vault import Note, VaultIndex


def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def tight(**kw: object) -> Measurement:
    base = {
        "metric": "lead time",
        "value": 100.0,
        "unit": "weeks",
        "as_of": days_ago(30),
        "source": "https://example.com/filing",
        "normal": 50.0,
    }
    return Measurement(**{**base, **kw})  # type: ignore[arg-type]


def full_legs(**over: object) -> list:
    """Three answered legs, all strong, so a test can weaken exactly one."""
    legs = [
        binding_leg([tight()]),
        durability_leg([Route(path="new fab", status="blocked")]),
        capture_leg(share_pct=90, pricing_power="demonstrated", pricing_evidence="+30% ASP, Q2"),
    ]
    for key, leg in over.items():
        legs = [leg if existing.key == key else existing for existing in legs]  # type: ignore[list-item]
    return legs


# --- binding: is it actually tight, and is that news? ------------------------


def test_a_measurement_past_normal_carries_the_leg() -> None:
    leg = binding_leg([tight(value=100.0, normal=50.0)])
    assert leg.score == 1.0, "double the normal lead time is a full claim"
    assert leg.detail["strongest"]["metric"] == "lead time"


def test_a_measurement_at_normal_scores_nothing() -> None:
    leg = binding_leg([tight(value=50.0, normal=50.0)])
    assert leg.score == 0.0, "at normal, nothing is constrained"


def test_a_stale_measurement_is_not_evidence_about_now() -> None:
    leg = binding_leg([tight(as_of=days_ago(400))])
    assert leg.score is None, "a year-old lead time is a fact about last year"
    assert any("months old" in q for q in leg.open_questions)


def test_freshness_decays_rather_than_cliff_edging() -> None:
    fresh = binding_leg([tight(as_of=days_ago(30))]).score
    middling = binding_leg([tight(as_of=days_ago(180))]).score
    assert fresh is not None and middling is not None
    assert fresh > middling > 0, "a six-month-old reading still counts, for less"


def test_a_measurement_without_a_baseline_cannot_carry_the_leg() -> None:
    leg = binding_leg([tight(normal=None)])
    assert leg.score is None
    assert any("normal market" in q for q in leg.open_questions)


def test_an_undated_measurement_is_refused_and_named() -> None:
    leg = binding_leg([tight(as_of="whenever")])
    assert leg.score is None
    assert any("no usable date" in q for q in leg.open_questions)


def test_the_strongest_reading_carries_it_not_the_average() -> None:
    """One live measurement of a sold-out line beats four stale gestures."""
    leg = binding_leg(
        [
            tight(metric="weak", value=55.0, normal=50.0),
            tight(metric="strong", value=100.0, normal=50.0),
            tight(metric="weak too", value=52.0, normal=50.0),
        ]
    )
    assert leg.score == 1.0
    assert leg.detail["strongest"]["metric"] == "strong"


def test_no_measurements_asks_for_one() -> None:
    leg = binding_leg([])
    assert leg.score is None
    assert any("lead time" in q for q in leg.open_questions)


# --- durability: can it be designed around? ---------------------------------


def test_an_open_workaround_caps_the_leg_however_many_blocked_paths_exist() -> None:
    leg = durability_leg(
        [
            Route(path="blocked A", status="blocked"),
            Route(path="blocked B", status="blocked"),
            Route(path="drop-in substitute, shipping today", status="open"),
        ]
    )
    assert leg.score is not None and leg.score <= 0.1, "the chain breaks at its weakest point"
    assert leg.detail["closest_workaround"]["path"].startswith("drop-in")


def test_capacity_arriving_soon_hurts_more_than_capacity_arriving_late() -> None:
    soon = durability_leg([Route(path="fab", status="building", eta_months=6)]).score
    late = durability_leg([Route(path="fab", status="building", eta_months=48)]).score
    assert soon is not None and late is not None
    assert soon < late, "a fix landing in six months is the thesis risk"


def test_building_without_a_date_is_flagged_as_unsizeable() -> None:
    leg = durability_leg([Route(path="fab", status="building")])
    assert any("actually arrive" in q for q in leg.open_questions)


def test_an_untested_constraint_is_unanswered_not_durable() -> None:
    leg = durability_leg([])
    assert leg.score is None, "nobody having tried to route around it proves nothing"
    assert any("designed around" in q for q in leg.open_questions)


def test_an_unknown_route_status_is_refused() -> None:
    with pytest.raises(ConstraintError, match="unknown route status"):
        durability_leg([Route(path="x", status="probably fine")])


# --- capture: who keeps the money? ------------------------------------------


def test_share_without_pricing_power_is_unanswered() -> None:
    leg = capture_leg(share_pct=95)
    assert leg.score is None, "holding every unit is not the same as pricing it"
    assert any("raised prices" in q for q in leg.open_questions)


def test_absent_pricing_power_collapses_the_leg_despite_total_share() -> None:
    leg = capture_leg(share_pct=100, pricing_power="absent")
    assert leg.score is not None and leg.score <= 0.1


def test_a_minority_holder_is_a_participant_not_a_gate() -> None:
    leg = capture_leg(share_pct=30, pricing_power="demonstrated", pricing_evidence="x")
    assert leg.score == 0.0


def test_demonstrated_pricing_power_wants_the_receipt() -> None:
    leg = capture_leg(share_pct=90, pricing_power="demonstrated")
    assert any("which quarter" in q for q in leg.open_questions)


def test_an_unknown_pricing_power_is_refused() -> None:
    with pytest.raises(ConstraintError, match="unknown pricing_power"):
        capture_leg(share_pct=90, pricing_power="vibes")


# --- the chain: multiplied, and the weakest leg picks the action -------------


def test_all_three_strong_supports_a_position() -> None:
    out = validate(full_legs())
    assert out["available"] is True
    assert out["label"] == "strong"
    assert out["structure"]["allowed"] == "the constraint supports a position"


def test_a_leaking_rent_kills_a_real_and_durable_shortage() -> None:
    """The failure this whole module exists to catch."""
    out = validate(full_legs(capture=capture_leg(share_pct=100, pricing_power="absent")))
    assert out["score"] < 0.15
    assert out["weakest_leg"] == "capture"
    assert out["structure"]["allowed"] == "buy the beneficiary, not the chokepoint"


def test_a_close_workaround_makes_it_a_dated_trade() -> None:
    out = validate(
        full_legs(durability=durability_leg([Route(path="fab", status="building", eta_months=4)]))
    )
    assert out["weakest_leg"] == "durability"
    assert out["structure"]["allowed"] == "a dated trade, not an investment"


def test_an_unmeasured_constraint_is_a_watchlist_item() -> None:
    out = validate(full_legs(binding=binding_leg([tight(value=51.0, normal=50.0)])))
    assert out["weakest_leg"] == "binding"
    assert out["structure"]["allowed"] == "watchlist, not a position"


def test_an_unanswered_leg_is_unavailable_not_zero() -> None:
    out = validate(full_legs(binding=binding_leg([])))
    assert out["available"] is False
    assert "score" not in out, "an unvalidated constraint must not read as a low score"
    assert out["unanswered"] == ["binding"]
    assert out["open_questions"]


def test_a_missing_requisite_is_refused() -> None:
    with pytest.raises(ConstraintError, match="missing requisite"):
        validate([binding_leg([tight()])])


def test_the_chain_is_a_product_not_an_average() -> None:
    """Two strong legs must not rescue one dead one."""
    out = validate(
        full_legs(capture=capture_leg(share_pct=40, pricing_power="absent")),
    )
    assert out["score"] < 0.05


# --- the curated catalogue --------------------------------------------------


def write_catalogue(tmp_path: Path, entries: list[dict]) -> Path:
    p = tmp_path / "constraints.json"
    p.write_text(json.dumps({"constraints": entries}), encoding="utf-8")
    cat.load_catalogue.cache_clear()
    return p


def minimal_entry(**over: object) -> dict:
    base = {
        "id": "hbm",
        "system": "intelligence",
        "name": "HBM supply",
        "scarce_object": "stacked DRAM with through-silicon vias",
        "why": "Accelerators cannot ship without it.",
        "names": [
            {"ticker": "A", "name": "Pure Co", "exposure": "all of it", "band": "pure"},
            {"ticker": "B", "name": "Conglom", "exposure": "one division", "band": "minor"},
            {"ticker": "C", "name": "Major Co", "exposure": "a segment", "band": "major"},
        ],
    }
    return {**base, **over}


def test_a_missing_catalogue_is_a_state_not_a_crash(tmp_path: Path) -> None:
    cat.load_catalogue.cache_clear()
    assert cat.load_catalogue(tmp_path / "absent.json") == ()


def test_names_rank_purest_exposure_first(tmp_path: Path) -> None:
    p = write_catalogue(tmp_path, [minimal_entry()])
    c = cat.load_catalogue(p)[0]
    assert [n.ticker for n in c.ranked_names()] == ["A", "C", "B"]


def test_a_sourced_revenue_share_breaks_a_tie_within_a_band(tmp_path: Path) -> None:
    p = write_catalogue(
        tmp_path,
        [
            minimal_entry(
                names=[
                    {
                        "ticker": "LO",
                        "name": "L",
                        "exposure": "x",
                        "band": "major",
                        "revenue_share_pct": 20,
                    },
                    {
                        "ticker": "HI",
                        "name": "H",
                        "exposure": "x",
                        "band": "major",
                        "revenue_share_pct": 60,
                    },
                    {"ticker": "UNK", "name": "U", "exposure": "x", "band": "major"},
                ]
            )
        ],
    )
    c = cat.load_catalogue(p)[0]
    assert [n.ticker for n in c.ranked_names()] == ["HI", "LO", "UNK"], (
        "an unsourced share sorts last rather than being guessed at"
    )


def test_an_unvalidated_curated_entry_says_so_rather_than_scoring_low(tmp_path: Path) -> None:
    p = write_catalogue(tmp_path, [minimal_entry()])
    out = cat.load_catalogue(p)[0].as_dict()
    assert out["validation"]["available"] is False
    assert out["source"] == "curated"
    assert out["validation"]["open_questions"]


def test_a_bad_band_names_the_offending_entry(tmp_path: Path) -> None:
    p = write_catalogue(
        tmp_path,
        [minimal_entry(names=[{"ticker": "X", "name": "X", "exposure": "x", "band": "biggish"}])],
    )
    with pytest.raises(ConstraintError.__mro__[1], match="band"):  # CatalogueError is a ValueError
        cat.load_catalogue(p)


def test_a_bad_system_is_refused(tmp_path: Path) -> None:
    p = write_catalogue(tmp_path, [minimal_entry(system="vibes")])
    with pytest.raises(cat.CatalogueError, match="system"):
        cat.load_catalogue(p)


def test_duplicate_ids_are_refused(tmp_path: Path) -> None:
    p = write_catalogue(tmp_path, [minimal_entry(), minimal_entry()])
    with pytest.raises(cat.CatalogueError, match="duplicate"):
        cat.load_catalogue(p)


def test_the_shipped_catalogue_loads_and_every_entry_is_wellformed() -> None:
    """The real config/constraints.json, so a bad edit fails here not in the UI."""
    cat.load_catalogue.cache_clear()
    entries = cat.load_catalogue()
    for c in entries:
        assert c.system in cat.SYSTEMS
        assert c.why and c.scarce_object
        for n in c.names:
            assert n.band in cat.EXPOSURE_BANDS
            assert n.exposure, f"{c.id}/{n.ticker} has no stated exposure"
        # Every measurement must be attributable, or it is an assertion.
        for m in c.measurements:
            assert m.source, f"{c.id}: measurement {m.metric!r} has no source"
            assert m.as_of, f"{c.id}: measurement {m.metric!r} has no date"
    cat.load_catalogue.cache_clear()


# --- derived from the vault -------------------------------------------------


def index_of(*notes: Note) -> VaultIndex:
    return VaultIndex(notes=list(notes), root="/tmp/x", built_at="now")


def note(title: str, *, tags: tuple[str, ...], body: str = "") -> Note:
    return Note(
        path=f"{title}.md", title=title, tags=tags, links=(), haystack=body.lower(), folder=""
    )


def test_a_dense_constraint_thread_is_proposed() -> None:
    notes = [
        note(f"Silver {i}", tags=("silver",), body="a structural shortage of deliverable metal")
        for i in range(MIN_NOTES)
    ]
    out = derive_candidates(index_of(*notes))
    assert [d.subject for d in out] == ["silver"]
    assert out[0].flagged_count == MIN_NOTES
    assert out[0].flagged_quotes[0]["term"] == "shortage"


def test_a_topic_you_write_about_without_scarcity_is_not_a_constraint() -> None:
    notes = [note(f"Note {i}", tags=("telco",), body="growth and demand") for i in range(8)]
    assert derive_candidates(index_of(*notes)) == []


def test_one_stray_mention_in_a_big_tag_does_not_qualify() -> None:
    """The bug the ratio gate exists for: #deeptech was 48 of 147 and buried silver."""
    notes = [
        note(f"N{i}", tags=("deeptech",), body="a note about margins and market share")
        for i in range(20)
    ]
    notes.append(note("Odd one", tags=("deeptech",), body="a genuine bottleneck"))
    out = derive_candidates(index_of(*notes))
    assert out == [], f"1 in 21 is below the {MIN_FLAGGED_RATIO:.0%} floor"


def test_a_negated_mention_still_matches_but_the_quote_shows_why() -> None:
    """What term matching cannot do, and why every hit carries your sentence.

    "there is no shortage" reads as a hit. Nothing short of real parsing would
    catch that, so the design shows the sentence instead of hiding the match
    behind a count — the negation is obvious the moment you read it.
    """
    notes = [
        note(f"N{i}", tags=("tinplate",), body="there is no shortage of supply")
        for i in range(MIN_NOTES)
    ]
    out = derive_candidates(index_of(*notes))
    assert out, "the match is not suppressed"
    assert "no shortage" in out[0].flagged_quotes[0]["quote"]


def test_scarcely_is_not_scarce() -> None:
    notes = [note(f"N{i}", tags=("x",), body="scarcely worth reading") for i in range(9)]
    assert derive_candidates(index_of(*notes)) == []


def test_a_thread_below_the_note_floor_is_not_proposed() -> None:
    notes = [
        note(f"N{i}", tags=("hbm",), body="sold out through 2027") for i in range(MIN_NOTES - 1)
    ]
    assert derive_candidates(index_of(*notes)) == []


def test_broad_tags_are_never_constraints() -> None:
    notes = [note(f"N{i}", tags=("macro", "the"), body="a global shortage") for i in range(9)]
    assert derive_candidates(index_of(*notes)) == []


def test_volume_times_density_beats_a_unanimous_small_sample() -> None:
    """17-of-19 is stronger evidence than 5-of-5, which pure ratio got backwards."""
    big = [
        note(f"Silver {i}", tags=("silver",), body="a deliverable shortage") for i in range(17)
    ] + [note(f"Silver pad {i}", tags=("silver",), body="just pricing") for i in range(2)]
    small = [note(f"Tiny {i}", tags=("tinytag",), body="a shortage") for i in range(5)]

    out = derive_candidates(index_of(*big, *small))
    assert [d.subject for d in out][0] == "silver"


def test_a_derived_candidate_is_never_scored() -> None:
    notes = [note(f"N{i}", tags=("silver",), body="a shortage of metal") for i in range(MIN_NOTES)]
    d = derive_candidates(index_of(*notes))[0].as_dict()

    assert d["source"] == "your notes"
    assert d["validation"]["available"] is False
    assert "score" not in d["validation"], "a note is not a measurement"
    assert len(d["validation"]["open_questions"]) == 3
    assert d["system"] is None, "your notes do not sort themselves into three systems"


def test_a_derived_candidate_quotes_your_own_words() -> None:
    notes = [
        note(
            f"N{i}",
            tags=("transformers",),
            body="utilities report a four year lead time on large units",
        )
        for i in range(MIN_NOTES)
    ]
    q = derive_candidates(index_of(*notes))[0].flagged_quotes[0]
    assert "lead time" in q["quote"]
    assert q["title"].startswith("N")


def test_an_empty_vault_proposes_nothing() -> None:
    assert derive_candidates(index_of()) == []


# --- capture under a market price rather than a concentrated holder ----------


def test_a_market_price_carries_capture_without_a_share() -> None:
    """A capacity auction pays every owner the same price; share is meaningless."""
    leg = capture_leg(
        pricing_power="demonstrated",
        pricing_evidence="cleared at the $325 cap, 14 Jul 2026",
        rent_mechanism="market_price",
    )
    assert leg.score == 1.0
    assert leg.detail["rent_mechanism"] == "market_price"


def test_a_market_price_with_no_receipt_stays_unanswered() -> None:
    """The evidence bar rises when price is the only thing carrying the leg."""
    leg = capture_leg(pricing_power="demonstrated", rent_mechanism="market_price")
    assert leg.score is None
    assert any("clearing price" in q for q in leg.open_questions)


def test_a_market_price_still_respects_weak_pricing_power() -> None:
    leg = capture_leg(
        pricing_power="absent",
        pricing_evidence="cleared at the floor",
        rent_mechanism="market_price",
    )
    assert leg.score is not None and leg.score <= 0.1


def test_concentration_remains_the_default() -> None:
    """The normal case is unchanged: no share, no answer."""
    leg = capture_leg(pricing_power="demonstrated", pricing_evidence="x")
    assert leg.score is None
    assert any("share of this chokepoint" in q for q in leg.open_questions)


def test_an_unknown_rent_mechanism_is_refused() -> None:
    with pytest.raises(ConstraintError, match="unknown rent_mechanism"):
        capture_leg(pricing_power="demonstrated", rent_mechanism="vibes")
