"""Curated comparable companies.

The bug these guard against is concrete: EDGAR's SIC 3571 put Socket Mobile and
One Stop Systems in Apple's peer set and left Microsoft out, so any multiple
drawn from that set was wrong before it was drawn.
"""

from __future__ import annotations

import json

import pytest

from hedge_fund.data.comps import (
    DEFAULT_COMPS_PATH,
    CuratedSet,
    apply_curated,
    load_curated,
)
from hedge_fund.data.models import PeerComparison


def _write(tmp_path, payload) -> "object":
    p = tmp_path / "comps.json"
    p.write_text(json.dumps(payload))
    return p


# ------------------------------------------------------------------
# Reading the file
# ------------------------------------------------------------------


def test_parses_peers_with_reasons(tmp_path):
    p = _write(
        tmp_path,
        {
            "comps": {
                "aapl": {
                    "as_of": "2026-09-12",
                    "peers": [
                        {"ticker": "msft", "reason": "platform scale"},
                        {"ticker": "GOOGL"},
                    ],
                }
            }
        },
    )
    got = load_curated(p)
    assert got["AAPL"].peers == ("MSFT", "GOOGL")
    assert got["AAPL"].reasons == {"MSFT": "platform scale"}
    assert got["AAPL"].as_of == "2026-09-12"


def test_drops_self_and_duplicates(tmp_path):
    # A ticker is not its own comparable, and a duplicate would be counted
    # twice in every average drawn from the set.
    p = _write(tmp_path, {"comps": {"AAPL": {"peers": ["AAPL", "MSFT", "msft", "DELL"]}}})
    assert load_curated(p)["AAPL"].peers == ("MSFT", "DELL")


def test_skips_entries_with_no_usable_peers(tmp_path):
    p = _write(tmp_path, {"comps": {"AAPL": {"peers": []}, "MSFT": {"peers": [{"nope": 1}]}}})
    assert load_curated(p) == {}


@pytest.mark.parametrize("payload", ["not json at all", json.dumps({"comps": "wrong shape"})])
def test_unreadable_file_falls_back_rather_than_failing(tmp_path, payload):
    # Comps are edited by hand, so the app has to survive a half-written file.
    p = tmp_path / "comps.json"
    p.write_text(payload)
    assert load_curated(p) == {}


def test_missing_file_is_not_an_error(tmp_path):
    assert load_curated(tmp_path / "absent.json") == {}


# ------------------------------------------------------------------
# Overlaying onto whatever the providers returned
# ------------------------------------------------------------------


def _auto(peers: list[str]) -> PeerComparison:
    return PeerComparison(
        ticker="AAPL",
        peers=peers,
        sector="Technology",
        industry="Consumer Electronics",
        metrics={t: {"pe_ratio": 1.0} for t in peers},
        source="edgar",
    )


def test_curated_set_replaces_the_sic_set_outright():
    # Blending would leave the vetted set diluted with SIC noise, which is no
    # longer a vetted set.
    curated = {"AAPL": CuratedSet("AAPL", ("MSFT", "GOOGL"), {"MSFT": "platform scale"})}
    out = apply_curated("AAPL", _auto(["SCKT", "OSS", "OMCL"]), curated)
    assert out.peers == ["MSFT", "GOOGL"]
    assert "SCKT" not in out.peers
    assert out.basis == "curated"
    assert out.vetted is True
    assert out.peer_reasons["MSFT"] == "platform scale"
    assert out.source == "curated+edgar"


def test_without_a_curated_set_the_automatic_one_is_labelled_unvetted():
    out = apply_curated("AAPL", _auto(["SCKT", "OSS"]), {})
    assert out.peers == ["SCKT", "OSS"]
    assert out.basis == "sic"
    assert out.vetted is False


def test_no_peers_at_all_reports_basis_none():
    out = apply_curated("AAPL", _auto([]), {})
    assert out.basis == "none"
    assert out.vetted is False


def test_nothing_to_work_with_returns_nothing():
    assert apply_curated("AAPL", None, {}) is None


def test_curated_set_stands_alone_when_no_provider_answered():
    curated = {"AAPL": CuratedSet("AAPL", ("MSFT",), {})}
    out = apply_curated(
        "AAPL",
        None,
        curated,
        fundamentals=lambda t: {"sector": "Technology", "industry": "Consumer Electronics"},
    )
    assert out.peers == ["MSFT"]
    assert out.sector == "Technology"
    assert out.source == "curated"


# ------------------------------------------------------------------
# Metrics: a curated set is useless without numbers to compare
# ------------------------------------------------------------------


def test_metrics_are_fetched_for_the_curated_set_and_the_subject():
    curated = {"AAPL": CuratedSet("AAPL", ("MSFT",), {})}
    calls: list[str] = []

    def fundamentals(t: str) -> dict:
        calls.append(t)
        return {"pe_ratio": 38.1, "market_cap": 1, "name": "ignored", "sector": "Technology"}

    out = apply_curated("AAPL", None, curated, fundamentals=fundamentals)
    assert calls[:2] == ["AAPL", "MSFT"]
    # Only comparison metrics travel: `name` is not a number to rank on.
    assert out.metrics["AAPL"] == {"pe_ratio": 38.1, "market_cap": 1}


def test_one_bad_symbol_does_not_empty_the_table():
    curated = {"AAPL": CuratedSet("AAPL", ("MSFT", "BROKEN"), {})}

    def fundamentals(t: str) -> dict:
        if t == "BROKEN":
            raise RuntimeError("provider down")
        if t == "MSFT":
            return {"error": "no data"}
        return {"pe_ratio": 38.1}

    out = apply_curated("AAPL", None, curated, fundamentals=fundamentals)
    assert out.peers == ["MSFT", "BROKEN"]  # still the set you curated
    assert set(out.metrics) == {"AAPL"}  # only the rows that had numbers


# ------------------------------------------------------------------
# The shipped file
# ------------------------------------------------------------------


def test_shipped_config_fixes_the_apple_peer_set():
    comps = load_curated(DEFAULT_COMPS_PATH)
    apple = comps["AAPL"]
    assert "MSFT" in apple.peers
    for junk in ("SCKT", "OSS", "OMCL"):
        assert junk not in apple.peers
    # Every curated name carries a stated reason: that is what makes it curation
    # rather than a second opinion with no argument attached.
    assert all(apple.reasons.get(t) for t in apple.peers)


def test_every_shipped_set_states_a_reason_for_every_name():
    for ticker, spec in load_curated(DEFAULT_COMPS_PATH).items():
        assert spec.peers, ticker
        for peer in spec.peers:
            assert spec.reasons.get(peer), f"{ticker} → {peer} has no reason"
