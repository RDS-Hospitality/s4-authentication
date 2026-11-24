from __future__ import annotations

import logging
from unittest import mock

import pytest

from s4_auth_flask import (
    AuthConfig,
    auth_headers,
    current_user,
    has_role,
    public,
    require_role,
)
from s4_auth_flask import roles as roles_module
from tests.test_flow import HTTPS, finish_login, start_login

HTML = {"Accept": "text/html,application/xhtml+xml"}


def sign_in(client, fake_idp, base_url=HTTPS, prefix="", **claims):
    _, q = start_login(client, base_url=base_url, prefix=prefix)
    token = fake_idp.id_token(nonce=q["nonce"], **claims)
    resp, _ = finish_login(
        client, fake_idp, q, base_url=base_url, id_token=token, prefix=prefix
    )
    return resp


@pytest.fixture
def app(make_app):
    app = make_app()

    @app.get("/reports")
    def reports():
        return "reports"

    @app.post("/submit")
    def submit():
        return "submitted"

    @app.get("/admin")
    @require_role("dash-admin")
    def admin():
        return "admin"

    @app.get("/me")
    def me():
        return current_user()

    @app.get("/headers")
    def headers():
        from flask import request

        return auth_headers(request.args["url"])

    @app.get("/hr")
    def hr():
        return {"a": has_role("a"), "b": has_role(["b", "c"])}

    @app.get("/open")
    @public
    def open_():
        return "open"

    return app


def test_unauthenticated_html_get_redirects_and_remembers_path(app):
    client = app.test_client()
    resp = client.get("/reports?x=1", base_url=HTTPS, headers=HTML)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/auth/login"
    with client.session_transaction(base_url=HTTPS) as s:
        assert s["s4.return_to"] == "/reports?x=1"


def test_deep_link_returns_to_original_path(app, fake_idp):
    client = app.test_client()
    client.get("/reports?x=1", base_url=HTTPS, headers=HTML)
    resp = sign_in(client, fake_idp)
    assert resp.status_code == 303
    assert resp.headers["Location"] == "/reports?x=1"


def test_deep_link_under_prefix_mount(make_app, fake_idp, config):
    cfg = AuthConfig(
        providers=("google",),
        user_pool_id=config.user_pool_id,
        client_id=config.client_id,
        cognito_domain=config.cognito_domain,
        base_url="https://x.example.com/dash",
        session_backend="memory",
    )
    app = make_app(cfg)

    @app.get("/r")
    def r():
        return "r"

    client = app.test_client()
    base = "https://x.example.com/dash"
    resp = client.get("/r", base_url=base, headers=HTML)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/dash/auth/login"
    done = sign_in(client, fake_idp, base_url=base)
    assert done.status_code == 303
    assert done.headers["Location"] == "/dash/r"


def test_unauthenticated_post_is_401_and_not_remembered(app):
    client = app.test_client()
    resp = client.post("/submit", base_url=HTTPS, headers=HTML)
    assert resp.status_code == 401
    assert b"submitted" not in resp.data
    with client.session_transaction(base_url=HTTPS) as s:
        assert "s4.return_to" not in s


def test_unauthenticated_json_get_is_401(app):
    resp = app.test_client().get(
        "/reports", base_url=HTTPS, headers={"Accept": "application/json"}
    )
    assert resp.status_code == 401
    assert b"reports" not in resp.data


def test_public_and_static_endpoints_pass(app):
    client = app.test_client()
    assert client.get("/open", base_url=HTTPS).status_code == 200
    assert client.get("/static/nothing.css", base_url=HTTPS).status_code == 404
    assert client.get("/auth/login", base_url=HTTPS).status_code == 302


def test_every_app_route_is_guarded_by_default(app):
    exempt = {"static", "open_", "index", "seed", "whoami"}
    client = app.test_client()
    checked = 0
    for rule in app.url_map.iter_rules():
        if rule.endpoint in exempt or rule.endpoint.startswith("s4_auth."):
            continue
        method = "POST" if "POST" in rule.methods else "GET"
        resp = client.open(rule.rule, method=method, base_url=HTTPS, headers=HTML)
        assert resp.status_code in (302, 401), rule.endpoint
        assert b"reports" not in resp.data and b"submitted" not in resp.data
        checked += 1
    assert checked >= 4


def test_store_failure_denies(app):
    client = app.test_client()
    inner = app.session_interface._inner
    with mock.patch.object(inner, "open_session", side_effect=RuntimeError("store down")):
        html = client.get("/reports", base_url=HTTPS, headers=HTML)
        plain = client.get("/reports", base_url=HTTPS)
    assert html.status_code == 302
    assert plain.status_code == 401
    assert b"reports" not in html.data + plain.data
    assert not html.headers.getlist("Set-Cookie")


def test_require_role_allows_and_denies(app, fake_idp):
    ok = app.test_client()
    sign_in(ok, fake_idp, hasura_allowed_roles=["dash-admin"])
    assert ok.get("/admin", base_url=HTTPS).status_code == 200
    no = app.test_client()
    sign_in(no, fake_idp, hasura_allowed_roles=["viewer"])
    assert no.get("/admin", base_url=HTTPS).status_code == 403


def test_missing_role_claim_logs_once(app, fake_idp, caplog):
    roles_module._warned_sinks.clear()
    client = app.test_client()
    sign_in(client, fake_idp)
    with caplog.at_level(logging.WARNING, logger="s4_auth_flask"):
        client.get("/reports", base_url=HTTPS)
        client.get("/reports", base_url=HTTPS)
    hits = [r for r in caplog.records if "hasura_allowed_roles" in r.getMessage()]
    assert len(hits) == 1


def test_require_role_rejects_empty_requirement():
    with pytest.raises(ValueError):
        require_role([])
    with pytest.raises(ValueError):
        require_role("")


def test_has_role_in_request(app, fake_idp):
    client = app.test_client()
    sign_in(client, fake_idp, hasura_allowed_roles=["a"])

    assert client.get("/hr", base_url=HTTPS).get_json() == {"a": True, "b": False}


def test_current_user_exposes_verified_claims(app, fake_idp):
    client = app.test_client()
    sign_in(client, fake_idp, hasura_allowed_roles=["dash-admin", "viewer"])
    user = client.get("/me", base_url=HTTPS).get_json()
    assert user["sub"] == "sub-123"
    assert user["email"] == "user@example.com"
    assert user["roles"] == ["dash-admin", "viewer"]


def test_auth_headers_only_for_allowlisted_urls(make_app, fake_idp, config):
    cfg = AuthConfig(
        providers=config.providers,
        user_pool_id=config.user_pool_id,
        client_id=config.client_id,
        cognito_domain=config.cognito_domain,
        base_url=config.base_url,
        session_backend="memory",
        graphql_urls=("https://api.example.com/v1/graphql",),
    )
    for conf, url, expect_bearer in (
        (cfg, "https://api.example.com/v1/graphql", True),
        (cfg, "https://evil.com/x", False),
        (config, "https://api.example.com/v1/graphql", False),
    ):
        app = make_app(conf)

        @app.get("/h")
        def h():
            from flask import request

            return auth_headers(request.args["url"])

        client = app.test_client()
        sign_in(client, fake_idp)
        body = client.get("/h", query_string={"url": url}, base_url=HTTPS).get_json()
        if expect_bearer:
            assert body["Authorization"].startswith("Bearer ")
            assert body["Authorization"].count(".") == 2
        else:
            assert body == {}


def test_view_under_adapter_endpoint_name_is_still_denied(app):
    app.add_url_rule(
        "/sneaky", endpoint="s4_auth.sneaky", view_func=lambda: "sneaky-body"
    )
    resp = app.test_client().get("/sneaky", base_url=HTTPS, headers=HTML)
    assert resp.status_code == 302
    assert b"sneaky-body" not in resp.data


@pytest.mark.parametrize(
    "bad", [{}, "a-string", ["x"], 7, {"email": "a@b.c"}, {"sub": ""}, {"sub": "  "}]
)
def test_malformed_claims_are_not_signed_in(app, bad):
    client = app.test_client()
    with client.session_transaction(base_url=HTTPS) as s:
        s["s4.claims"] = bad
    resp = client.get("/reports", base_url=HTTPS, headers=HTML)
    assert resp.status_code == 302
    assert b"reports" not in resp.data
    login = client.get("/auth/login", base_url=HTTPS)
    assert login.status_code == 302
    assert "/oauth2/authorize" in login.headers["Location"]
