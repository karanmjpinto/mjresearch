"""Run persistence, content addressing, and drift detection."""

from __future__ import annotations

import pytest

from hedge_fund.runs import RunRecord, compare_runs, get_run, get_snapshot, list_runs, save_run
from hedge_fund.runs.hashing import canonical_json, run_key, snapshot_hash

SNAP = {
    "ticker": "AAPL",
    "price": {"current": 316.83},
    "fundamentals": {"pe_ratio": 31.2},
    "provenance": {"slots": {"price:AAPL": {"fetched_at": "2026-01-01T00:00:00+00:00"}}},
}


def _record(**kw):
    base = dict(
        ticker="AAPL",
        mode="single",
        snapshot=SNAP,
        model="ollama:llama3.2",
        model_params={"temperature": 0.0, "seed": 7},
        prompt_sha256="p" * 64,
        output={"conviction_score": 61, "stance": "HOLD", "time_horizon": "medium_term"},
    )
    base.update(kw)
    return RunRecord(**base)


# ----------------------------------------------------------------------
# Hashing
# ----------------------------------------------------------------------


def test_canonical_json_is_key_order_independent():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_snapshot_hash_ignores_fetch_metadata():
    a = {
        "ticker": "A",
        "price": {"current": 1.0},
        "provenance": {"slots": {"x": {"fetched_at": "t1"}}},
    }
    b = {
        "ticker": "A",
        "price": {"current": 1.0},
        "provenance": {"slots": {"x": {"fetched_at": "t2"}}},
    }
    assert snapshot_hash(a) == snapshot_hash(b)


def test_snapshot_hash_tracks_the_data():
    a = {"ticker": "A", "price": {"current": 1.0}}
    b = {"ticker": "A", "price": {"current": 1.01}}
    assert snapshot_hash(a) != snapshot_hash(b)


def test_run_key_covers_every_determined_input():
    base = dict(
        snapshot_sha256="s", prompt_sha256="p", model="m", params={"seed": 7}, mode="single"
    )
    same = run_key(**base)
    assert run_key(**base) == same
    assert run_key(**{**base, "model": "other"}) != same
    assert run_key(**{**base, "params": {"seed": 8}}) != same
    assert run_key(**{**base, "mode": "committee"}) != same


# ----------------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------------


def test_save_and_retrieve_a_run(isolated_db):
    uid = save_run(_record())
    assert uid

    run = get_run(uid)
    assert run["ticker"] == "AAPL"
    assert run["mode"] == "single"
    assert run["output"]["stance"] == "HOLD"
    assert run["model_params"]["seed"] == 7
    assert run["snapshot"]["fundamentals"]["pe_ratio"] == 31.2


def test_snapshot_is_stored_once_and_reused(isolated_db):
    save_run(_record())
    save_run(_record(persona_id="warren_buffett", mode="persona"))

    with isolated_db() as session:
        from hedge_fund.db.models import ResearchSnapshot

        assert session.query(ResearchSnapshot).count() == 1


def test_changed_data_creates_a_new_snapshot(isolated_db):
    save_run(_record())
    save_run(_record(snapshot={**SNAP, "price": {"current": 999.0}}))

    with isolated_db() as session:
        from hedge_fund.db.models import ResearchSnapshot

        assert session.query(ResearchSnapshot).count() == 2


def test_snapshot_can_be_rehydrated_for_replay(isolated_db):
    uid = save_run(_record())
    digest = get_run(uid)["snapshot_sha256"]

    restored = get_snapshot(digest)
    assert restored["fundamentals"]["pe_ratio"] == 31.2
    assert snapshot_hash(restored) == digest, "a replayed snapshot must hash identically"


def test_list_runs_filters(isolated_db):
    save_run(_record(ticker="AAPL"))
    save_run(_record(ticker="MSFT"))
    save_run(_record(ticker="AAPL", mode="committee"))

    assert len(list_runs()) == 3
    assert len(list_runs(ticker="AAPL")) == 2
    assert len(list_runs(mode="committee")) == 1


def test_persistence_failure_does_not_raise(isolated_db, monkeypatch):
    """A broken store degrades observability, never the analysis."""
    import hedge_fund.runs.store as store

    def boom():
        raise RuntimeError("db is gone")

    monkeypatch.setattr(store, "SessionLocal", boom)
    assert save_run(_record()) is None


def test_persistence_can_be_switched_off(isolated_db, monkeypatch):
    from hedge_fund.settings import settings

    monkeypatch.setattr(settings, "research_run_persistence", False)
    assert save_run(_record()) is None


def test_missing_run_returns_none(isolated_db):
    assert get_run("no-such-uid") is None


# ----------------------------------------------------------------------
# Comparison — the eval primitive
# ----------------------------------------------------------------------


def test_identical_runs_compare_clean(isolated_db):
    a = save_run(_record())
    b = save_run(_record())
    diff = compare_runs(a, b)

    assert diff["same_inputs"] is True
    assert diff["identical_conclusion"] is True
    assert diff["nondeterminism_detected"] is False


def test_same_inputs_different_conclusion_is_flagged(isolated_db):
    a = save_run(_record())
    b = save_run(_record(output={"conviction_score": 20, "stance": "SELL"}))
    diff = compare_runs(a, b)

    assert diff["same_inputs"] is True
    assert diff["nondeterminism_detected"] is True
    assert diff["field_diffs"]["stance"] == {"a": "HOLD", "b": "SELL"}


def test_different_data_is_not_nondeterminism(isolated_db):
    """A changed conclusion on changed data is expected, not a defect."""
    a = save_run(_record())
    b = save_run(
        _record(
            snapshot={**SNAP, "price": {"current": 100.0}},
            output={"conviction_score": 20, "stance": "SELL"},
        )
    )
    diff = compare_runs(a, b)

    assert diff["same_snapshot"] is False
    assert diff["nondeterminism_detected"] is False


def test_prose_differences_do_not_count_as_disagreement(isolated_db):
    a = save_run(
        _record(output={"conviction_score": 61, "stance": "HOLD", "investment_thesis": "one"})
    )
    b = save_run(
        _record(output={"conviction_score": 61, "stance": "HOLD", "investment_thesis": "two"})
    )
    assert compare_runs(a, b)["identical_conclusion"] is True


def test_compare_reports_missing_runs(isolated_db):
    uid = save_run(_record())
    assert compare_runs(uid, "ghost")["error"] == "run_not_found"


@pytest.mark.parametrize("mode", ["single", "persona", "committee", "plan"])
def test_all_modes_persist(isolated_db, mode):
    assert save_run(_record(mode=mode)) is not None
