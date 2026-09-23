"""The Factors tab: JKP return statistics and one company's position on them.

Most of what can go wrong here is quiet. A missing month read as zero, a
factor whose long leg is the *low* end ranked the wrong way round, an
unmeasured theme shown as a neutral 50 — each renders as a perfectly plausible
chart. These tests pin those specific failures.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from hedge_fund.api.main import app
from hedge_fund.factors import exposure, jkp

client = TestClient(app)


# ── Statistics ────────────────────────────────────────────────────────────


def test_stats_annualise_mean_vol_sharpe_and_t():
    rets = [0.01, -0.005] * 30  # 60 months
    s = jkp.stats(rets)
    assert s is not None
    mean = 0.0025
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / 59)
    assert s["months"] == 60
    assert s["ann_return"] == pytest.approx(mean * 12)
    assert s["ann_vol"] == pytest.approx(sd * math.sqrt(12))
    assert s["sharpe"] == pytest.approx(mean / sd * math.sqrt(12))
    assert s["t_stat"] == pytest.approx(mean / (sd / math.sqrt(60)))


def test_missing_months_are_skipped_not_zero():
    with_gaps = [0.02, None] * 30
    assert jkp.stats(with_gaps)["months"] == 30
    assert jkp.stats(with_gaps)["ann_return"] == pytest.approx(0.24)


def test_too_short_a_sample_has_no_sharpe():
    assert jkp.stats([0.01] * (jkp.MIN_MONTHS - 1)) is None


# ── The committed JKP data ────────────────────────────────────────────────


def test_every_theme_is_served_in_the_fixed_order():
    got = jkp.theme_rows()
    assert [t["id"] for t in got["themes"]] == list(jkp.THEME_ORDER)
    assert got["months"][0] <= "1926-12"
    for t in got["themes"]:
        assert t["stats"]["full"]["months"] > 500, t["id"]
        # The returns run from `start` to the last month without gaps in index.
        assert t["start"] + len(t["returns"]) <= len(got["months"])


def test_every_factor_has_a_theme_a_name_and_a_sign():
    d = jkp.load()
    assert len(d["factors"]) == 153
    details = d["details"]["factors"]
    for fid, s in d["factors"].items():
        assert fid in details, fid
        assert details[fid]["theme"] in jkp.THEME_ORDER, fid
        assert s["direction"] in (1, -1), fid


def test_factor_rows_split_around_the_original_sample():
    got = jkp.factor_rows("momentum")
    assert got is not None
    mom = next(f for f in got["factors"] if f["id"] == "ret_12_1")
    lo, hi = mom["in_sample_years"]
    assert (lo, hi) == (1965, 1989)  # Jegadeesh and Titman (1993)
    # 25 years in-sample; everything from 1990 to the data's last month after.
    last_y, last_m = int(got["last_month"][:4]), int(got["last_month"][5:7])
    assert mom["in_sample"]["months"] == 25 * 12
    assert mom["post_sample"]["months"] == (last_y - 1990) * 12 + last_m


def test_unknown_theme_is_none():
    assert jkp.factor_rows("astrology") is None


# ── Exposure ──────────────────────────────────────────────────────────────


def test_percentile_is_mid_rank():
    ref = [1.0, 2.0, 3.0, 4.0]
    assert exposure.percentile(0.5, ref) == 0
    assert exposure.percentile(5.0, ref) == 100
    assert exposure.percentile(2.0, ref) == pytest.approx(37.5)


def _universe(n: int = 40) -> dict[str, dict]:
    return {
        f"T{i:02d}": {"market_cap": float(i + 1) * 1e9, "price_to_book": float(i + 1)}
        for i in range(n)
    }


def test_a_short_leg_characteristic_is_flipped():
    """Size: JKP go long *small* caps, so the biggest name scores near zero."""
    uni = _universe()
    p = exposure.profile("T39", universe=uni, sources=[])
    me = next(c for c in p["characteristics"] if c["id"] == "market_equity")
    assert me["direction"] == -1
    assert me["percentile"] > 95
    assert me["score"] == pytest.approx(100 - me["percentile"])


def test_a_long_leg_characteristic_is_not_flipped():
    """Book-to-market: long the high end. The lowest P/B is the cheapest."""
    uni = _universe()
    p = exposure.profile("T00", universe=uni, sources=[])
    bm = next(c for c in p["characteristics"] if c["id"] == "be_me")
    assert bm["direction"] == 1
    assert bm["score"] == bm["percentile"] > 95


def test_an_unmeasured_theme_is_none_not_fifty():
    p = exposure.profile("T10", universe=_universe(), sources=[])
    by = {t["id"]: t for t in p["themes"]}
    assert by["seasonality"]["score"] is None
    assert by["seasonality"]["measured"] == 0
    assert by["size"]["score"] is not None


def test_too_few_peers_reports_the_value_but_no_rank():
    p = exposure.profile("T01", universe=_universe(exposure.MIN_PEERS - 1), sources=[])
    me = next(c for c in p["characteristics"] if c["id"] == "market_equity")
    assert me["value"] == 2e9
    assert me["percentile"] is None and me["score"] is None


def test_every_characteristic_is_a_real_jkp_characteristic():
    known = jkp.load()["factors"]
    for c in exposure.CHARACTERISTICS:
        assert c.id in known, c.id


def test_every_theme_is_named_in_the_docs():
    """The reference section lists the themes; a new one must not appear silently."""
    from pathlib import Path

    docs = (
        (Path(__file__).resolve().parents[1] / "frontend" / "src" / "content" / "docs.ts")
        .read_text(encoding="utf-8")
        .lower()
    )
    for name in jkp.load()["details"]["themes"].values():
        assert name.lower() in docs, name


# ── Routes ────────────────────────────────────────────────────────────────


def test_themes_route():
    r = client.get("/api/factors/themes")
    assert r.status_code == 200
    body = r.json()
    assert len(body["themes"]) == 13
    assert body["source"]["url"] == "https://jkpfactors.com"


def test_theme_route_404s_on_an_unknown_theme():
    assert client.get("/api/factors/themes/astrology").status_code == 404
    assert client.get("/api/factors/themes/value").status_code == 200


def test_profile_rejects_a_malformed_ticker():
    assert client.get("/api/factors/profile/$$$").status_code == 400


def test_profile_without_live_fetch_for_an_uncached_name(monkeypatch):
    monkeypatch.setattr(exposure, "reference_universe", lambda: (_universe(), []))
    r = client.get("/api/factors/profile/ZZZZ", params={"live": "false"})
    assert r.status_code == 200
    body = r.json()
    assert body["in_reference"] is False
    assert all(t["score"] is None for t in body["themes"])
