from __future__ import annotations

import time

import pytest
from flask import request

from s4_auth_flask import current_user, extension, public, require_role
from tests.test_flow import HTTPS
from tests.test_guards import HTML, sign_in

RAN = []


@pytest.fixture
def client(make_app, fake_idp):
    app = make_app()
    RAN.clear()

    @app.get("/reports")
    def reports():
        return "reports"

    @app.route("/mutate", methods=["POST", "PUT", "PATCH", "DELETE"])
    def mutate():
        RAN.append(request.method)
        return "done"

    @app.get("/who")
    @public
    def who():
        return {"user": current_user()}

    @app.get("/admin-public")
    @public
    @require_role("admin")
    def admin_public():
        return "admin"

    c = app.test_client()
    sign_in(c, fake_idp, hasura_allowed_roles=["admin"])
    return c


@pytest.fixture
def clock(monkeypatch):
    state = {"offset": 0.0}
    monkeypatch.setattr(extension, "_now", lambda: time.time() + state["offset"])

    def advance(seconds):
        state["offset"] += seconds

    return advance


def test_guarded_response_is_no_store(client):
    resp = client.get("/reports", base_url=HTTPS, headers=HTML)
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "no-store"


def test_guarded_deny_response_is_no_store(make_app):
    app = make_app()

    @app.get("/reports")
    def reports():
        return "reports"

    resp = app.test_client().get("/reports", base_url=HTTPS, headers=HTML)
    assert resp.status_code == 302
    assert resp.headers["Cache-Control"] == "no-store"


def test_public_response_is_unaffected(client):
    resp = client.get("/who", base_url=HTTPS)
    assert resp.status_code == 200
    assert "no-store" not in resp.headers.get("Cache-Control", "")


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_same_origin_unsafe_method_passes(client, method):
    resp = client.open("/mutate", method=method, base_url=HTTPS, headers={"Origin": HTTPS})
    assert resp.status_code == 200
    assert RAN == [method]


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.com"},
        {"Origin": "null"},
        {},
        {"Referer": "https://evil.com/x"},
    ],
)
def test_unsafe_method_without_same_origin_is_403_and_view_does_not_run(client, headers):
    resp = client.post("/mutate", base_url=HTTPS, headers=headers)
    assert resp.status_code == 403
    assert RAN == []


def test_same_origin_referer_only_passes(client):
    resp = client.post("/mutate", base_url=HTTPS, headers={"Referer": HTTPS + "/reports"})
    assert resp.status_code == 200
    assert RAN == ["POST"]


def test_safe_method_needs_no_origin(client):
    assert client.get("/reports", base_url=HTTPS, headers=HTML).status_code == 200


def test_public_view_sees_ended_session_after_idle_timeout(client, clock):
    assert client.get("/who", base_url=HTTPS).get_json()["user"] is not None
    clock(31 * 60)
    assert client.get("/who", base_url=HTTPS).get_json()["user"] is None


def test_require_role_on_public_view_denies_after_idle_timeout(client, clock):
    assert client.get("/admin-public", base_url=HTTPS).status_code == 200
    clock(31 * 60)
    resp = client.get("/admin-public", base_url=HTTPS, headers=HTML)
    assert resp.status_code in (302, 401, 403)
