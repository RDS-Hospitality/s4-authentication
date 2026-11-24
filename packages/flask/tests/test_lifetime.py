from __future__ import annotations

import time
from urllib.parse import parse_qs

import pytest

from s4_auth_flask import extension
from tests.test_flow import HTTPS
from tests.test_guards import HTML, sign_in


@pytest.fixture
def clock(monkeypatch):
    state = {"offset": 0.0}
    monkeypatch.setattr(extension, "_now", lambda: time.time() + state["offset"])

    def advance(seconds):
        state["offset"] += seconds

    return advance


@pytest.fixture
def app(make_app):
    app = make_app()

    @app.get("/reports")
    def reports():
        return "reports"

    return app


@pytest.fixture
def client(app, fake_idp):
    client = app.test_client()
    sign_in(client, fake_idp)
    return client


def get(client, path="/reports"):
    return client.get(path, base_url=HTTPS, headers=HTML)


def refresh_reply(fake_idp, **overrides):
    body = {
        "id_token": fake_idp.id_token(),
        "access_token": fake_idp.access_token(),
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    body.update(overrides)
    fake_idp.set_token_reply(body)


def stay_active(client, clock, minutes):
    """Advance in 20-minute steps, requesting each time, so the idle timeout never trips."""
    for _ in range(minutes // 20):
        clock(20 * 60)
        get(client)


def test_idle_31_minutes_requires_reauth(client, clock):
    clock(31 * 60)
    resp = get(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/auth/login")


def test_idle_29_minutes_still_signed_in(client, clock, fake_idp):
    refresh_reply(fake_idp)
    clock(29 * 60)
    assert get(client).status_code == 200


def test_expired_access_token_refreshes_silently(client, clock, fake_idp):
    stay_active(client, clock, 40)
    fake_idp.token_requests.clear()
    refresh_reply(fake_idp)
    clock(20 * 60)
    resp = get(client)
    assert resp.status_code == 200
    assert len(fake_idp.token_requests) == 1
    body = parse_qs(fake_idp.token_requests[0].body)
    assert body["grant_type"] == ["refresh_token"]
    assert body["refresh_token"] == ["refresh-secret-value"]


def test_refresh_keeps_existing_refresh_token(client, clock, fake_idp):
    stay_active(client, clock, 40)
    fake_idp.token_requests.clear()
    refresh_reply(fake_idp)
    stay_active(client, clock, 160)
    assert len(fake_idp.token_requests) >= 2
    for req in fake_idp.token_requests:
        assert parse_qs(req.body)["refresh_token"] == ["refresh-secret-value"]


def test_refreshed_id_token_is_verified(client, clock, fake_idp):
    from joserfc.jwk import RSAKey

    other = RSAKey.generate_key(2048, {"kid": "test-key", "use": "sig", "alg": "RS256"})
    stay_active(client, clock, 40)
    refresh_reply(fake_idp, id_token=fake_idp.id_token(signer=other))
    clock(20 * 60)
    resp = get(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/auth/login")
    clock(60)
    assert get(client).status_code == 302


def test_revoked_refresh_token_ends_session(client, clock, fake_idp):
    stay_active(client, clock, 40)
    fake_idp.set_token_reply({"error": "invalid_grant"}, 400)
    clock(20 * 60)
    resp = get(client)
    assert resp.status_code < 500
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/auth/login")


def test_activity_written_at_most_once_a_minute(app, client, clock, monkeypatch):
    interface = app.session_interface._inner
    saves = []
    original = interface._upsert_session
    monkeypatch.setattr(
        interface, "_upsert_session", lambda *a, **k: (saves.append(1), original(*a, **k))[1]
    )
    clock(61)
    for _ in range(5):
        clock(5)
        assert get(client).status_code == 200
    assert len(saves) == 1
