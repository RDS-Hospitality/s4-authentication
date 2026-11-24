from __future__ import annotations

from urllib.parse import parse_qs

import pytest

from tests.test_flow import sid_cookie
from tests.test_flow import HTTPS
from tests.test_guards import HTML, sign_in


@pytest.fixture
def client(make_app, fake_idp):
    app = make_app()

    @app.get("/reports")
    def reports():
        return "reports"

    client = app.test_client()
    sign_in(client, fake_idp)
    return client


def logout(client, **headers):
    return client.post("/auth/logout", base_url=HTTPS, headers=headers)


def test_logout_is_post_only(client):
    assert client.get("/auth/logout", base_url=HTTPS).status_code == 405


def test_cross_origin_logout_is_refused(client):
    assert logout(client, Origin="https://evil.com").status_code == 403
    assert client.get("/reports", base_url=HTTPS).status_code == 200


def test_cross_origin_referer_is_refused(client):
    assert logout(client, Referer="https://evil.com/x").status_code == 403


def test_logout_without_origin_or_referer_is_refused(client):
    assert logout(client).status_code == 403


def test_logout_revokes_clears_and_redirects(client, fake_idp, config):
    old_cookie = client.get_cookie("s4_session").value
    resp = logout(client, Origin=HTTPS)
    assert resp.status_code == 303
    assert resp.headers["Location"] == config.logout_url
    body = parse_qs(fake_idp.revoke_requests[0].body)
    assert body["token"] == ["refresh-secret-value"]
    assert body["client_id"] == [config.client_id]
    assert "Expires=Thu, 01 Jan 1970" in sid_cookie(resp)
    client.set_cookie("s4_session", old_cookie, domain="localhost")
    replay = client.get("/reports", base_url=HTTPS, headers=HTML)
    assert replay.status_code == 302
    assert replay.headers["Location"].endswith("/auth/login")


def test_logout_accepts_same_origin_referer(client):
    assert logout(client, Referer=HTTPS + "/reports").status_code == 303


def test_logout_still_completes_when_revoke_fails(client, idp_mock, config):
    idp_mock.replace(idp_mock.POST, config.revoke_url, status=500)
    resp = logout(client, Origin=HTTPS)
    assert resp.status_code == 303
    assert "Expires=Thu, 01 Jan 1970" in sid_cookie(resp)


def test_logout_still_completes_on_network_error(client, idp_mock, config):
    idp_mock.replace(idp_mock.POST, config.revoke_url, body=ConnectionError("down"))
    resp = logout(client, Origin=HTTPS)
    assert resp.status_code == 303
    assert "Expires=Thu, 01 Jan 1970" in sid_cookie(resp)
