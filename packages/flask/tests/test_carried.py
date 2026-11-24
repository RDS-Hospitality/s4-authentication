from __future__ import annotations

import time
from dataclasses import replace
from datetime import timedelta

import pytest
from flask import Flask

from s4_auth_flask import AuthConfig, S4Auth, current_user
from tests.test_flow import HTTPS, finish_login, start_login
from tests.test_guards import sign_in


def test_dynamodb_backend_without_resource_is_a_clear_error(config):
    cfg = replace(config, session_backend="dynamodb")
    with pytest.raises(ValueError, match="session_resource"):
        S4Auth(Flask(__name__), cfg)


def _login(make_app, fake_idp, config, *, expires_in=3600, **claims):
    app = make_app(config)

    @app.get("/me")
    def me():
        return {"user": current_user()}

    client = app.test_client()
    _, q = start_login(client)
    token = fake_idp.id_token(nonce=q["nonce"], **claims)
    finish_login(client, fake_idp, q, id_token=token)
    return app, client


def test_current_user_includes_default_role(make_app, fake_idp, config):
    _, client = _login(make_app, fake_idp, config, hasura_default_role="site")
    assert client.get("/me", base_url=HTTPS).get_json()["user"]["default_role"] == "site"


def test_default_role_claim_name_is_configurable(make_app, fake_idp, config):
    cfg = replace(config, default_role_claim="my_default")
    _, client = _login(make_app, fake_idp, cfg, my_default="ops")
    assert client.get("/me", base_url=HTTPS).get_json()["user"]["default_role"] == "ops"


def _expires_at(client):
    with client.session_transaction(base_url=HTTPS) as s:
        return s["s4.tokens"]["expires_at"]


def test_access_ttl_caps_expires_at(make_app, fake_idp, config):
    cfg = replace(config, access_ttl=timedelta(minutes=10))
    _, client = _login(make_app, fake_idp, cfg)
    assert _expires_at(client) <= time.time() + 600 + 5


def test_id_token_exp_caps_expires_at(make_app, fake_idp, config):
    _, client = _login(make_app, fake_idp, config, exp=int(time.time()) + 120)
    assert _expires_at(client) <= time.time() + 120 + 5


def test_refresh_expiry_is_capped_by_access_ttl(make_app, fake_idp, config, monkeypatch):
    from s4_auth_flask import extension

    cfg = replace(config, access_ttl=timedelta(minutes=10))
    app, client = _login(make_app, fake_idp, cfg)
    offset = {"v": 0.0}
    monkeypatch.setattr(extension, "_now", lambda: time.time() + offset["v"])
    offset["v"] = 9.5 * 60  # inside the refresh skew of the 10-minute expiry
    fake_idp.set_token_reply(
        {"id_token": fake_idp.id_token(), "access_token": fake_idp.access_token(), "expires_in": 3600}
    )
    assert client.get("/me", base_url=HTTPS).status_code == 200
    assert _expires_at(client) <= time.time() + offset["v"] + 600 + 5


def test_http_timeout_is_set_on_the_oauth_client(make_app):
    app = make_app()
    assert app.extensions["s4_auth"].oauth.s4.client_kwargs["default_timeout"] == 10


def test_guard_runs_before_earlier_registered_before_request_hooks(config, idp_mock):
    app = Flask(__name__)
    ran = []

    @app.before_request
    def early():
        ran.append("early")

    @app.get("/x")
    def x():
        return "x"

    S4Auth(app, config)
    resp = app.test_client().get("/x", base_url=HTTPS, headers={"Accept": "application/json"})
    assert resp.status_code == 401
    assert ran == []


@pytest.mark.parametrize("route", ["/\\evil.com", "/a\x00b", "/a\nb", "//evil.com", "/\\\\x"])
def test_post_login_route_rejects_unsafe_values(config, route):
    with pytest.raises(ValueError):
        replace(config, post_login_route=route)
