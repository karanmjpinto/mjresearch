"""The guard on the four routes that can spend money.

This exists because of a real exposure rather than a hypothetical one. The
hosted deployment runs `llm_provider=openai` against a paid gateway, had no
authentication and no rate limit, and CORS was the only thing in front of it —
which constrains browsers and does nothing whatsoever to `curl`. Any stranger
with the URL could have started `POST /api/autoresearch/run`, which is a loop,
and billed it to the owner.

What each test is really asserting is that the control cannot be talked past:

  - a disabled deployment refuses even when a valid key is presented
  - a wrong key is refused, and a missing one too
  - the limit counts per client, so one caller cannot exhaust another's
  - none of it engages by default, so a local checkout is unaffected

The money routes are asserted by name. If someone adds a fifth one, the last
test here fails, which is the only way this file can keep up with the app.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hedge_fund.api.guards import LLM_ACCESS, reset_rate_limits
from hedge_fund.api.main import app as real_app
from hedge_fund.settings import settings

#: The routes that invoke a model. Kept here so the guarantee is stated in one
#: place and checked against the live app below.
MONEY_ROUTES = {
    ("POST", "/api/research/check"),
    ("POST", "/api/research/plan"),
    ("POST", "/api/simulation/backtest"),
    ("POST", "/api/autoresearch/run"),
}


@pytest.fixture
def guarded() -> TestClient:
    """A tiny app with one guarded route, so nothing calls a real model."""
    app = FastAPI()

    @app.post("/spend", dependencies=[LLM_ACCESS])
    async def spend() -> dict[str, bool]:
        return {"spent": True}

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    """Defaults are permissive; each test opts into the control it exercises."""
    monkeypatch.setattr(settings, "llm_endpoints_enabled", True)
    monkeypatch.setattr(settings, "llm_access_key", None)
    monkeypatch.setattr(settings, "llm_rate_limit_per_hour", 0)
    reset_rate_limits()
    yield
    reset_rate_limits()


# --- the default: a local checkout is unchanged ------------------------


def test_wide_open_by_default_so_local_use_is_unaffected(guarded):
    """The whole design rests on this: no config, no friction, free model."""
    assert guarded.post("/spend").status_code == 200


# --- switched off entirely ---------------------------------------------


def test_disabled_deployment_refuses(guarded, monkeypatch):
    monkeypatch.setattr(settings, "llm_endpoints_enabled", False)
    r = guarded.post("/spend")
    assert r.status_code == 503
    assert "runs on your" in r.json()["detail"] or "locally" in r.json()["detail"]


def test_a_valid_key_cannot_re_enable_a_disabled_deployment(guarded, monkeypatch):
    """Order of checks is load-bearing, not incidental.

    If the key were checked first, a leaked key would undo the owner's decision
    to stop serving models at all.
    """
    monkeypatch.setattr(settings, "llm_endpoints_enabled", False)
    monkeypatch.setattr(settings, "llm_access_key", "right")
    assert guarded.post("/spend", headers={"X-API-Key": "right"}).status_code == 503


# --- the key ------------------------------------------------------------


def test_missing_and_wrong_keys_are_refused(guarded, monkeypatch):
    monkeypatch.setattr(settings, "llm_access_key", "right")
    assert guarded.post("/spend").status_code == 401
    assert guarded.post("/spend", headers={"X-API-Key": "wrong"}).status_code == 401
    assert guarded.post("/spend", headers={"X-API-Key": ""}).status_code == 401


def test_the_right_key_passes(guarded, monkeypatch):
    monkeypatch.setattr(settings, "llm_access_key", "right")
    assert guarded.post("/spend", headers={"X-API-Key": "right"}).status_code == 200


def test_a_near_miss_is_still_a_miss(guarded, monkeypatch):
    """Guards against a prefix comparison creeping in."""
    monkeypatch.setattr(settings, "llm_access_key", "right-and-long")
    assert guarded.post("/spend", headers={"X-API-Key": "right"}).status_code == 401
    assert guarded.post("/spend", headers={"X-API-Key": "right-and-longer"}).status_code == 401


# --- the rate limit -----------------------------------------------------


def test_the_limit_bites_after_the_allowance(guarded, monkeypatch):
    monkeypatch.setattr(settings, "llm_rate_limit_per_hour", 3)
    for _ in range(3):
        assert guarded.post("/spend").status_code == 200
    r = guarded.post("/spend")
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0, "a 429 without Retry-After is a guess for the caller"


def test_the_limit_is_per_client_not_global(guarded, monkeypatch):
    """One visitor must not be able to lock everyone else out."""
    monkeypatch.setattr(settings, "llm_rate_limit_per_hour", 2)
    for _ in range(2):
        guarded.post("/spend", headers={"X-Forwarded-For": "1.1.1.1"})
    assert guarded.post("/spend", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
    assert guarded.post("/spend", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200


def test_the_forwarded_client_is_the_first_hop(guarded, monkeypatch):
    """Behind a proxy the socket is the proxy, so every caller would share one
    bucket and the first visitor would spend everyone's allowance."""
    monkeypatch.setattr(settings, "llm_rate_limit_per_hour", 1)
    guarded.post("/spend", headers={"X-Forwarded-For": "9.9.9.9, 10.0.0.1"})
    assert (
        guarded.post("/spend", headers={"X-Forwarded-For": "9.9.9.9, 10.0.0.9"}).status_code == 429
    )


def test_a_rejected_call_does_not_consume_the_allowance(guarded, monkeypatch):
    """A refused request must not count, or a blocked caller could be kept
    blocked indefinitely by their own retries."""
    monkeypatch.setattr(settings, "llm_rate_limit_per_hour", 2)
    monkeypatch.setattr(settings, "llm_access_key", "right")
    for _ in range(5):
        assert guarded.post("/spend", headers={"X-API-Key": "wrong"}).status_code == 401
    assert guarded.post("/spend", headers={"X-API-Key": "right"}).status_code == 200
    assert guarded.post("/spend", headers={"X-API-Key": "right"}).status_code == 200
    assert guarded.post("/spend", headers={"X-API-Key": "right"}).status_code == 429


def test_zero_means_no_limit(guarded, monkeypatch):
    monkeypatch.setattr(settings, "llm_rate_limit_per_hour", 0)
    for _ in range(25):
        assert guarded.post("/spend").status_code == 200


# --- the app actually wires it up --------------------------------------


def test_every_money_route_on_the_real_app_is_guarded():
    """The point of the whole file. A new model-invoking route added without
    the dependency shows up here rather than on a bill.
    """
    from hedge_fund.api.guards import require_llm_access

    seen = set()
    for route in real_app.routes:
        methods = getattr(route, "methods", set()) or set()
        for m in methods:
            if (m, getattr(route, "path", "")) in MONEY_ROUTES:
                deps = [
                    d.call
                    for d in getattr(route.dependant, "dependencies", [])
                    if hasattr(d, "call")
                ]
                assert require_llm_access in deps, f"{m} {route.path} can spend money unguarded"
                seen.add((m, route.path))

    assert seen == MONEY_ROUTES, f"routes missing from the app: {MONEY_ROUTES - seen}"


def test_the_free_routes_are_not_gated():
    """Over-gating would break the published site's read-only overview, which
    is the part that is meant to work for everyone."""
    from hedge_fund.api.guards import require_llm_access

    for route in real_app.routes:
        path = getattr(route, "path", "")
        if path in {"/api/health", "/api/setup", "/api/screeners", "/api/runs"}:
            deps = [
                d.call for d in getattr(route.dependant, "dependencies", []) if hasattr(d, "call")
            ]
            assert require_llm_access not in deps, f"{path} should stay free to call"
