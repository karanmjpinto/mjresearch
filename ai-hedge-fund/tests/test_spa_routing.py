"""Serving the frontend: deep links, and the two routes that collided.

Both bugs these cover were live on the deployed site, and both had the same
shape — a default that is right for one host and wrong for this one.

`StaticFiles(html=True)` answers an unknown path with `404.html`, and the
frontend ships one for GitHub Pages, where a static host cannot route
`/dashboard` to `index.html`. Served from here that workaround looped: its
`segmentCount = 1` assumes the app lives one segment deep (the repo name), so
at a domain root `/dashboard` became `/dashboard/?p=/`, 404'd, and grew another
`~and~q=p=/` every pass — about a thousand requests per page load and a blank
screen.

And FastAPI puts Swagger at `/docs`, which is where this app serves its own
reference section. The framework's route won, so the page that says which
numbers are computed and which are written was the one page a visitor could
not reach.

Neither failed loudly. The first looked like a hung page, the second like a
working page — which is why they are pinned here rather than left to a manual
click.
"""

from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def served(tmp_path, monkeypatch):
    """The app with a built frontend behind it, as the deployment runs it."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>MJ Research</title><div id=root>")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)")
    # The GitHub Pages workaround that caused the loop. Present on purpose: the
    # fallback has to win over it.
    (dist / "404.html").write_text("<script>var segmentCount = 1;</script>")

    monkeypatch.setenv("STATIC_DIR", str(dist))
    import hedge_fund.api.main as main

    importlib.reload(main)
    client = TestClient(main.app)
    yield client
    monkeypatch.delenv("STATIC_DIR", raising=False)
    importlib.reload(main)


# --- deep links -------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/dashboard", "/screeners", "/screeners/bolton-contrarian", "/research/AAPL", "/docs"],
)
def test_a_deep_link_serves_the_app(served, path):
    """A shared link has to open the app, not a redirect that never lands."""
    r = served.get(path)
    assert r.status_code == 200, f"{path} did not serve the app"
    assert "MJ Research" in r.text
    assert "segmentCount" not in r.text, f"{path} served the GitHub Pages 404 shim"


def test_the_redirect_shim_is_never_what_a_visitor_gets(served):
    """The loop is the failure mode; assert on its signature directly."""
    r = served.get("/dashboard")
    assert "?p=/" not in r.text
    assert "~and~" not in r.text


def test_the_entry_point_still_works(served):
    r = served.get("/")
    assert r.status_code == 200 and "MJ Research" in r.text


# --- what must NOT fall back ------------------------------------------


def test_a_missing_asset_stays_a_404(served):
    """Returning HTML for a missing script turns a build error into a baffling
    parse error somewhere else entirely."""
    for path in ["/assets/index-deadbeef.js", "/fonts/nope.woff2", "/splatter.svg"]:
        assert served.get(path).status_code == 404, f"{path} should 404, not serve a page"


def test_a_real_asset_is_still_served(served):
    r = served.get("/assets/index-abc123.js")
    assert r.status_code == 200 and "console.log" in r.text


def test_an_unknown_api_path_stays_a_404(served):
    """`/api` belongs to the router. A wrong endpoint answering with HTML would
    read as success to anything expecting JSON."""
    r = served.get("/api/nope")
    assert r.status_code == 404
    assert "MJ Research" not in r.text


# --- the /docs collision ----------------------------------------------


def test_docs_belongs_to_the_frontend(served):
    """The reference section, not Swagger UI."""
    r = served.get("/docs")
    assert r.status_code == 200
    assert "swagger" not in r.text.lower(), "Swagger UI is squatting on the frontend's /docs"


def test_swagger_moved_under_api(served):
    assert served.get("/api/docs").status_code == 200
    assert "swagger" in served.get("/api/docs").text.lower()


def test_the_schema_moved_with_it(served):
    r = served.get("/api/openapi.json")
    assert r.status_code == 200
    assert json.loads(r.text)["info"]["title"] == "AI Hedge Fund API"


def test_the_api_still_answers_under_the_frontend(served):
    """The mount is at `/`, so it could shadow the router if ordering slipped."""
    r = served.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
