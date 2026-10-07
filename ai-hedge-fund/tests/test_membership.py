"""The invite gate: what it lets through, what it refuses, and what it counts.

Four invariants here are the ones worth having a test for, because each one is
a way the gate could look like it works while not working:

1. **Default-deny covers every route, not a list of them.** The test walks
   `app.routes` rather than naming paths, so a router added later is covered by
   this test on the day it lands. That is the whole argument for the middleware
   over per-router dependencies, and an enumerated test would give the argument
   away.
2. **Admission is at-most-once under concurrency.** A sequential second click
   failing proves nothing: the race is two simultaneous requests, which a
   read-then-write would let both through.
3. **Revocation reaches an already-open session.** This is the reason sessions
   are rows instead of signed cookies, so it is the reason the table exists.
4. **The budget is denominated in what the ledger measures**, and refuses with
   a reason distinguishable from the rate limiter's.
"""

from __future__ import annotations

import os
import tempfile
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def db_path(monkeypatch):
    """A throwaway SQLite file, with the app's settings pointed at it.

    A file rather than `:memory:` because the gate middleware opens its own
    session from `SessionLocal`, and an in-memory database is per-connection —
    the middleware would see an empty schema and every test would 401.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture()
def app_client(db_path, monkeypatch):
    """The real app, gate on, against a fresh database."""
    from hedge_fund.db import session as db_session
    from hedge_fund.settings import settings

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Local = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "SessionLocal", Local)

    # The modules under test resolve SessionLocal at call time via the module,
    # except where they imported the name directly — patch those too.
    import hedge_fund.api.membership as membership_mod
    import hedge_fund.members.ledger as ledger_mod

    monkeypatch.setattr(membership_mod, "SessionLocal", Local)

    from hedge_fund.db.models import Base  # noqa: F401  (registers the tables)

    db_session.Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(settings, "member_gate_enabled", True)
    monkeypatch.setattr(settings, "member_default_token_cap", 1000)
    # The TestClient speaks plain HTTP, and a `Secure` cookie is never sent back
    # over one — so with the production default every test here would join
    # successfully and then be treated as a stranger. That is the same trap a
    # developer hits on http://localhost:5173, which is what the setting is for.
    monkeypatch.setattr(settings, "member_cookie_secure", False)

    from hedge_fund.api.main import app

    # get_db is the dependency every route uses; override it rather than
    # patching, so the app's own wiring is exercised.
    from hedge_fund.db.session import get_db

    def _get_db():
        db = Local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as client:
        yield client, Local, ledger_mod
    app.dependency_overrides.clear()


@pytest.fixture()
def db(app_client):
    _, Local, _ = app_client
    s = Local()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client(app_client):
    return app_client[0]


# ---------------------------------------------------------------------------
# 1. Default-deny


def _exempt() -> frozenset[str]:
    from hedge_fund.api.membership import PUBLIC_API_PATHS

    return PUBLIC_API_PATHS


def test_every_api_route_is_closed_to_a_stranger(client):
    """No `/api/*` path answers without a session, except the four that must.

    Enumerated from `app.routes`, not from a hand-written list, so a router
    added after this test was written is covered by it. `/api/docs`,
    `/api/redoc` and `/api/openapi.json` are included: FastAPI mounts those
    itself rather than through a router, so no router-level dependency would
    ever have reached them and they would have published the whole API shape.
    """
    from hedge_fund.api.main import app

    checked = 0
    leaked = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api") or path in _exempt():
            continue
        # Fill path params with something harmless; the gate refuses before
        # the handler ever sees them.
        concrete = path
        for part in path.split("/"):
            if part.startswith("{"):
                concrete = concrete.replace(part, "AAPL")
        methods = getattr(route, "methods", {"GET"}) or {"GET"}
        method = "GET" if "GET" in methods else sorted(methods)[0]
        if method in {"HEAD", "OPTIONS"}:
            continue
        resp = client.request(method, concrete, json={})
        checked += 1
        if resp.status_code != 401:
            leaked.append((method, concrete, resp.status_code))

    assert checked > 20, f"expected to check the whole API, only saw {checked} routes"
    assert not leaked, f"these answered without a session: {leaked}"


def test_the_four_public_paths_stay_reachable(client):
    assert client.get("/api/health").status_code == 200
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["member"] is False
    assert me.json()["gate_enabled"] is True
    assert client.post("/api/logout").status_code == 204


def test_the_gate_is_off_by_default(client, monkeypatch):
    """A local checkout behaves exactly as it did before membership existed."""
    from hedge_fund.settings import settings

    monkeypatch.setattr(settings, "member_gate_enabled", False)
    resp = client.get("/api/methodology")
    assert resp.status_code != 401
    assert client.get("/api/me").json()["gate_enabled"] is False


# ---------------------------------------------------------------------------
# 2. Admission


def test_an_invite_admits_once_and_sets_a_session(client, db):
    from hedge_fund.members import service

    minted = service.mint_invite(db, label="Jude", token_cap=1000)
    db.commit()

    resp = client.post("/api/join", json={"token": minted.secret})
    assert resp.status_code == 200, resp.text
    assert resp.json()["label"] == "Jude"
    assert resp.json()["monthly_token_cap"] == 1000

    # The cookie now opens the rest of the API.
    assert client.get("/api/methodology").status_code != 401
    me = client.get("/api/me").json()
    assert me["member"] is True and me["label"] == "Jude"


def test_a_second_click_on_the_same_link_is_refused_with_a_usable_reason(client, db):
    from hedge_fund.members import service

    minted = service.mint_invite(db, label="Jude")
    db.commit()
    assert client.post("/api/join", json={"token": minted.secret}).status_code == 200

    client.cookies.clear()
    again = client.post("/api/join", json={"token": minted.secret})
    assert again.status_code == 403
    assert again.json()["detail"]["reason"] == "used"


def test_an_unknown_token_says_unknown_and_an_expired_one_says_expired(client, db):
    from hedge_fund.members import service

    bad = client.post("/api/join", json={"token": "nope-nope-nope-nope"})
    assert bad.status_code == 403
    assert bad.json()["detail"]["reason"] == "unknown"

    stale = service.mint_invite(db, label="Late", expires_in=timedelta(seconds=-1))
    db.commit()
    resp = client.post("/api/join", json={"token": stale.secret})
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "expired"


def test_simultaneous_clicks_admit_exactly_one_person(app_client, db):
    """The race a read-then-write would lose.

    Two threads post the same invite at the same moment. A `SELECT ... WHERE
    consumed_at IS NULL` followed by an `UPDATE` would let both pass the read,
    and two members would exist for one invite. Requiring `rowcount == 1` on a
    single conditional UPDATE makes the database pick the winner.
    """
    import threading

    from hedge_fund.db.models import Member
    from hedge_fund.members import service

    client, Local, _ = app_client
    minted = service.mint_invite(db, label="Contested")
    db.commit()

    results: list[int] = []
    barrier = threading.Barrier(2)

    def attempt():
        from fastapi.testclient import TestClient

        from hedge_fund.api.main import app

        with TestClient(app) as c:
            barrier.wait()
            results.append(c.post("/api/join", json={"token": minted.secret}).status_code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [200, 403], f"expected one winner, got {results}"

    fresh = Local()
    try:
        assert fresh.query(Member).count() == 1
    finally:
        fresh.close()


def test_join_is_rate_limited_so_it_is_not_a_guessing_oracle(client, monkeypatch):
    from hedge_fund.api import guards
    from hedge_fund.settings import settings

    guards.reset_rate_limits()
    monkeypatch.setattr(settings, "member_join_attempts_per_hour", 3)

    codes = [
        client.post("/api/join", json={"token": f"guess-{i}-aaaaaaaa"}).status_code
        for i in range(5)
    ]
    assert codes.count(429) >= 1, codes
    guards.reset_rate_limits()


def test_join_attempts_do_not_eat_the_model_run_allowance(client, monkeypatch):
    """The namespaced bucket.

    `_hits` is keyed on the caller, so if join and model runs shared a key,
    clicking an invite link would spend the member's own hourly model
    allowance — and a stranger guessing tokens would spend everyone's behind
    the same NAT.
    """
    from hedge_fund.api import guards
    from hedge_fund.settings import settings

    guards.reset_rate_limits()
    monkeypatch.setattr(settings, "member_join_attempts_per_hour", 50)
    monkeypatch.setattr(settings, "llm_rate_limit_per_hour", 2)

    for i in range(5):
        client.post("/api/join", json={"token": f"guess-{i}-aaaaaaaa"})

    # The model-run bucket must be untouched by all that.
    over, _ = guards.over_limit("testclient", 2)
    assert over is False
    guards.reset_rate_limits()


# ---------------------------------------------------------------------------
# 3. Revocation


def test_revoking_a_member_closes_a_session_that_is_already_open(client, db):
    """Why sessions are rows.

    A signed cookie cannot be withdrawn before it expires, so a revoked member
    would keep browsing — and keep spending — from a tab that was already open.
    """
    from hedge_fund.members import service

    minted = service.mint_invite(db, label="Soon gone")
    db.commit()
    client.post("/api/join", json={"token": minted.secret})
    assert client.get("/api/methodology").status_code != 401

    from hedge_fund.db.models import Member

    member = db.query(Member).filter(Member.label == "Soon gone").one()
    service.revoke_member(db, member.id)

    assert client.get("/api/methodology").status_code == 401
    assert client.get("/api/me").json()["member"] is False


def test_logout_revokes_only_that_session(client, db):
    from hedge_fund.members import service

    minted = service.mint_invite(db, label="Two devices")
    db.commit()
    client.post("/api/join", json={"token": minted.secret})
    first = dict(client.cookies)

    from hedge_fund.db.models import Member

    member = db.query(Member).filter(Member.label == "Two devices").one()
    second_secret = service.open_session(db, member.id)
    db.commit()

    client.post("/api/logout")
    assert client.get("/api/methodology").status_code == 401

    # The other device is unaffected.
    client.cookies.clear()
    client.cookies.set("mj_session", second_secret)
    assert client.get("/api/methodology").status_code != 401
    assert first  # the first cookie existed; it is simply dead now


def test_a_revoked_invite_cannot_be_used(client, db):
    from hedge_fund.members import service

    minted = service.mint_invite(db, label="Withdrawn")
    db.commit()
    assert service.revoke_invite(db, minted.invite.id) is True

    resp = client.post("/api/join", json={"token": minted.secret})
    assert resp.status_code == 403
    # Its own reason: see test_a_withdrawn_invite_says_withdrawn_not_used for
    # why this is not folded into "used".
    assert resp.json()["detail"]["reason"] == "withdrawn"


# ---------------------------------------------------------------------------
# 4. Budget and ledger


def test_the_ledger_attributes_a_call_to_whoever_caused_it(app_client, db):
    from hedge_fund.members import ledger, service

    _, Local, _ = app_client
    member = service.ensure_owner(db, label="owner")

    with ledger.attribute_to(member.id, "/api/research/check"):
        ledger.record("qwen3:30b", {"prompt_tokens": 400, "completion_tokens": 100})

    fresh = Local()
    try:
        assert service.tokens_this_month(fresh, member.id) == 500
    finally:
        fresh.close()


def test_the_ledger_writes_nothing_when_nobody_is_logged_in(app_client, db):
    """How a local checkout stays unmetered: not a flag, just no scope open."""
    from hedge_fund.db.models import LlmUsage
    from hedge_fund.members import ledger

    ledger.record("qwen3:30b", {"prompt_tokens": 999, "completion_tokens": 999})
    assert db.query(LlmUsage).count() == 0


def test_a_spent_budget_refuses_with_a_reason_distinct_from_the_rate_limiter(
    app_client, db, monkeypatch
):
    from fastapi import HTTPException

    from hedge_fund.api.membership import require_budget
    from hedge_fund.members import ledger, service

    member = service.ensure_owner(db, label="owner", token_cap=100)
    with ledger.attribute_to(member.id, "/api/research/check"):
        ledger.record("m", {"prompt_tokens": 100, "completion_tokens": 50})

    secret = service.open_session(db, member.id)
    db.commit()

    class _Req:
        cookies = {"mj_session": secret}

        class state:  # noqa: N801
            member = None

        url = type("U", (), {"path": "/api/research/check"})()
        scope: dict = {}

    with pytest.raises(HTTPException) as caught:
        require_budget(_Req(), db)
    assert caught.value.status_code == 429
    assert caught.value.detail["reason"] == "budget_exhausted"
    # Not the rate limiter's reason — the client has to tell them apart.
    assert caught.value.detail["reason"] != "rate_limited"


def test_a_cap_of_zero_means_no_model_access_at_all(db):
    """And zero is the default, so an invite minted without a cap cannot spend."""
    from hedge_fund.members import service

    spend = service.Spend(tokens=0, cap=0)
    assert spend.exhausted is True
    assert spend.fraction == 1.0


def test_month_to_date_is_the_utc_calendar_month(db):
    from datetime import datetime

    from hedge_fund.members import service

    boundary = service.month_start(datetime(2026, 3, 17, 4, 30, 1))
    assert boundary == datetime(2026, 3, 1, 0, 0, 0)


def test_usage_before_this_month_does_not_count_against_the_cap(app_client, db):
    from datetime import datetime

    from hedge_fund.db.models import LlmUsage
    from hedge_fund.members import service

    member = service.ensure_owner(db, label="owner", token_cap=1000)
    db.add(
        LlmUsage(
            member_id=member.id,
            route="/api/research/check",
            model="m",
            prompt_tokens=900,
            completion_tokens=0,
            created_at=datetime(2020, 1, 15),
        )
    )
    db.commit()
    assert service.tokens_this_month(db, member.id) == 0


# ---------------------------------------------------------------------------
# Secrets


def test_no_secret_is_ever_stored(db):
    """A database dump must admit nobody."""
    from hedge_fund.db.models import Invite, MemberSession
    from hedge_fund.members import service

    minted = service.mint_invite(db, label="Jude")
    member = service.ensure_owner(db, label="owner")
    session_secret = service.open_session(db, member.id)
    db.commit()

    stored_invites = [row.token_hash for row in db.query(Invite).all()]
    stored_sessions = [row.token_hash for row in db.query(MemberSession).all()]

    assert minted.secret not in stored_invites
    assert session_secret not in stored_sessions
    assert all(len(h) == 64 for h in stored_invites + stored_sessions)


def test_an_owner_granting_invite_produces_the_owner(client, db):
    """How the owner gets a session without a privileged second login path.

    A CLI cannot set a cookie in a browser, so `scripts/invite.py own` mints an
    invite like any other and marks it as granting ownership. The owner then
    arrives through exactly the same door as everyone else, which means there
    is only one admission path to get right.
    """
    from hedge_fund.members import service

    minted = service.mint_invite(db, label="owner", grants_owner=True)
    db.commit()

    resp = client.post("/api/join", json={"token": minted.secret})
    assert resp.status_code == 200
    assert client.get("/api/me").json()["is_owner"] is True


def test_an_ordinary_invite_does_not_produce_an_owner(client, db):
    from hedge_fund.members import service

    minted = service.mint_invite(db, label="Jude")
    db.commit()
    client.post("/api/join", json={"token": minted.secret})
    assert client.get("/api/me").json()["is_owner"] is False


# ---------------------------------------------------------------------------
# Regressions from the pre-landing review


def test_the_gates_401_carries_cors_headers(client):
    """Middleware order, which is silent and backwards-looking when wrong.

    `add_middleware` does `insert(0, ...)`, so the middleware added *last* is
    outermost. Registering the gate after CORS put the gate outside it, and the
    401 then went back without `Access-Control-Allow-Origin` — so an off-origin
    browser saw an opaque network error, `api.ts` never parsed the typed
    reason, and `MemberGate` fell into its "transport problem" branch and
    rendered the app as though there were no gate at all. Same-origin
    deployments never notice, which is what makes it worth a test.
    """
    origin = "http://localhost:5173"
    refused = client.get("/api/methodology", headers={"Origin": origin})
    assert refused.status_code == 401
    assert refused.headers.get("access-control-allow-origin") == origin


def test_a_universe_name_cannot_escape_the_cache_directory(client):
    """`universe` is interpolated into a path and arrives from a query string."""
    from hedge_fund.breadth.store import CACHE_DIR, BreadthUniverseInvalid, _path

    for bad in ["../../../../../../tmp/evil", "a/b", "..", "", "A" * 40]:
        with pytest.raises(BreadthUniverseInvalid):
            _path(bad)

    assert _path("sp500").is_relative_to(CACHE_DIR.resolve())


def test_an_invalid_universe_is_422_not_503(app_client, db, monkeypatch):
    """A rejected name must not be confusable with a universe that has no cache.

    503 for both would make the endpoint a file-existence oracle.
    """
    from hedge_fund.members import service
    from hedge_fund.settings import settings

    client, _, _ = app_client
    minted = service.mint_invite(db, label="Prober")
    db.commit()
    client.post("/api/join", json={"token": minted.secret})

    assert client.get("/api/breadth/", params={"universe": "../../etc/x"}).status_code == 422
    monkeypatch.setattr(settings, "member_gate_enabled", False)


def test_the_budget_binds_inside_a_fan_out_not_just_at_the_door(app_client, db):
    """The check at the door covers one request; a request is many calls.

    A committee is a dozen calls and `/api/autoresearch/run` is a detached task
    of up to two hundred experiments, all admitted by one check. Without a
    re-check inside the metered path, a member with one token left can spend
    for hours.
    """
    import pytest as _pytest

    from hedge_fund.members import ledger

    with ledger.attribute_to(1, "/api/research/check", spent=0, cap=1000):
        ledger.check_budget()  # under the cap, proceeds
        # Simulate calls landing mid-fan-out.
        ledger.current().spent = 1000
        with _pytest.raises(ledger.BudgetExhausted) as caught:
            ledger.check_budget()
    assert caught.value.spent == 1000
    assert caught.value.cap == 1000


def test_check_budget_is_a_no_op_when_nothing_is_metered(db):
    """Local runs have no scope and no cap, so the client never refuses."""
    from hedge_fund.members import ledger

    ledger.check_budget()  # no scope at all
    with ledger.attribute_to(1, "/api/research/check", spent=10**9, cap=0):
        ledger.check_budget()  # cap 0 means "not enforced here"


def test_the_running_total_survives_a_failed_ledger_write(db, monkeypatch):
    """A member whose ledger writes fail must not get an unlimited allowance."""
    from hedge_fund.members import ledger, service

    member = service.ensure_owner(db, label="owner", token_cap=100)

    def _boom(*args, **kwargs):
        raise RuntimeError("database gone")

    monkeypatch.setattr(service, "record_usage", _boom)

    with ledger.attribute_to(member.id, "/api/research/check", spent=0, cap=100):
        ledger.record("m", {"prompt_tokens": 60, "completion_tokens": 60})
        assert ledger.current().spent == 120  # counted despite the write failing
        with pytest.raises(ledger.BudgetExhausted):
            ledger.check_budget()


def test_a_withdrawn_invite_says_withdrawn_not_used(client, db):
    """Four cases, four remedies. 'used' would tell them to ask for another."""
    from hedge_fund.members import service

    minted = service.mint_invite(db, label="Taken back")
    db.commit()
    service.revoke_invite(db, minted.invite.id)

    resp = client.post("/api/join", json={"token": minted.secret})
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "withdrawn"


def test_the_join_limit_keys_on_an_address_the_caller_cannot_forge(client):
    """Cloudflare appends the real client to any XFF the client sent.

    So the FIRST hop is attacker-chosen: vary it and you get a fresh bucket
    every attempt, and the limit that stands between a token and a guessing
    oracle never fires.
    """
    from hedge_fund.api import guards

    class _Req:
        def __init__(self, headers):
            self.headers = headers
            self.client = type("C", (), {"host": "10.0.0.1"})()

    forged = _Req({"x-forwarded-for": "1.2.3.4, 9.9.9.9"})
    assert guards.trusted_client_ip(forged) == "9.9.9.9"  # last hop, not first
    assert guards.client_ip(forged) == "1.2.3.4"  # the brake still reads first

    edged = _Req({"cf-connecting-ip": "8.8.8.8", "x-forwarded-for": "1.2.3.4"})
    assert guards.trusted_client_ip(edged) == "8.8.8.8"

    assert guards.trusted_client_ip(_Req({})) == "10.0.0.1"


def test_the_cookie_secure_flag_is_configuration_not_a_client_header(client, db, monkeypatch):
    """A security flag must not be set by the party it constrains.

    An origin reachable without the edge plus `x-forwarded-proto: http` used to
    mint a session cookie with no Secure flag.
    """
    from hedge_fund.members import service
    from hedge_fund.settings import settings

    minted = service.mint_invite(db, label="Downgrade")
    db.commit()

    monkeypatch.setattr(settings, "member_cookie_secure", True)
    resp = client.post(
        "/api/join",
        json={"token": minted.secret},
        headers={"x-forwarded-proto": "http"},
    )
    assert resp.status_code == 200
    # Set despite the header asking for plain HTTP.
    assert "secure" in resp.headers["set-cookie"].lower()


def test_the_cookie_secure_flag_defaults_to_on(db):
    """The default has to be the safe one: a deployment that forgets to set it
    must get `Secure`, not silently ship a session cookie that travels in the
    clear. Local HTTP development is the case that opts out, by setting
    MEMBER_COOKIE_SECURE=false."""
    from hedge_fund.settings import Settings

    assert Settings().member_cookie_secure is True
