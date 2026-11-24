from __future__ import annotations

import requests
import responses as responses_lib

from tests.test_flow import HTTPS, start_login


def _break_store(app):
    def boom(*a, **k):
        raise RuntimeError("store down")

    app.session_interface._inner.open_session = boom


def test_idp_error_shows_401_page_with_escaped_description_and_no_redirect(make_app):
    client = make_app().test_client()
    _, q = start_login(client)
    resp = client.get(
        "/auth/callback",
        query_string={
            "error": "access_denied",
            "error_description": "<script>alert(1)</script> not allowed",
            "state": q["state"],
        },
        base_url=HTTPS,
    )
    assert resp.status_code == 401
    assert "Location" not in resp.headers
    body = resp.get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt; not allowed" in body
    assert "<script>" not in body
    assert 'href="/auth/login"' in body


def test_idp_error_without_description_shows_error_code(make_app):
    client = make_app().test_client()
    start_login(client)
    resp = client.get("/auth/callback?error=access_denied", base_url=HTTPS)
    assert resp.status_code == 401
    assert "access_denied" in resp.get_data(as_text=True)


def test_state_mismatch_still_redirects_to_login(make_app):
    client = make_app().test_client()
    start_login(client)
    resp = client.get("/auth/callback?code=abc&state=wrong", base_url=HTTPS)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/auth/login"


def test_network_error_at_token_exchange_is_503_without_redirect(make_app, idp_mock, fake_idp):
    client = make_app().test_client()
    _, q = start_login(client)
    fake_idp.set_token_reply(lambda request: (_ for _ in ()).throw(requests.ConnectionError("down")))
    resp = client.get(f"/auth/callback?code=abc&state={q['state']}", base_url=HTTPS)
    assert resp.status_code == 503
    assert "Location" not in resp.headers


def test_login_with_unusable_session_is_503_without_redirect(make_app):
    app = make_app()
    _break_store(app)
    resp = app.test_client().get("/auth/login", base_url=HTTPS)
    assert resp.status_code == 503
    assert "Location" not in resp.headers


def test_callback_with_unusable_session_is_503_without_redirect(make_app):
    app = make_app()
    _break_store(app)
    resp = app.test_client().get("/auth/callback?code=abc&state=x", base_url=HTTPS)
    assert resp.status_code == 503
    assert "Location" not in resp.headers
