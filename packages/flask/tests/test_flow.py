from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from joserfc.jwk import RSAKey

from s4_auth_flask.config import AuthConfig

HTTPS = "https://localhost"


def query(location: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}


def sid_cookie(response, name="s4_session"):
    for header in response.headers.getlist("Set-Cookie"):
        if header.startswith(name + "="):
            return header
    return None


def start_login(client, base_url=HTTPS, prefix=""):
    resp = client.get(f"{prefix}/auth/login", base_url=base_url)
    assert resp.status_code == 302
    return resp, query(resp.headers["Location"])


def finish_login(client, fake_idp, params, base_url=HTTPS, *, id_token=None, prefix=""):
    tokens = {
        "id_token": id_token
        or fake_idp.id_token(nonce=params["nonce"]),
        "access_token": fake_idp.access_token(),
        "refresh_token": "refresh-secret-value",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    fake_idp.set_token_reply(tokens)
    resp = client.get(
        f"{prefix}/auth/callback?code=abc&state={params['state']}", base_url=base_url
    )
    return resp, tokens


def test_login_redirect_uses_code_pkce_s256(make_app, config):
    client = make_app().test_client()
    resp, q = start_login(client)
    assert resp.headers["Location"].startswith(
        f"https://{config.cognito_domain}/oauth2/authorize?"
    )
    assert q["response_type"] == "code"
    assert q["code_challenge"]
    assert q["code_challenge_method"] == "S256"
    assert q["scope"] == "openid email profile"
    assert q["identity_provider"] == "Google"
    assert q["redirect_uri"] == config.callback_url
    assert "token" not in q["response_type"]


def test_callback_redirects_303_to_post_login_route(make_app, fake_idp):
    client = make_app().test_client()
    _, q = start_login(client)
    resp, _ = finish_login(client, fake_idp, q)
    assert resp.status_code == 303
    assert resp.headers["Location"] == "/"


def test_hostile_return_path_falls_back(make_app, fake_idp):
    client = make_app().test_client()
    client.get("/seed?to=//evil.com", base_url=HTTPS)
    _, q = start_login(client)
    resp, _ = finish_login(client, fake_idp, q)
    assert resp.status_code == 303
    assert resp.headers["Location"] == "/"


def test_session_cookie_flags_and_rotation(make_app, fake_idp):
    client = make_app().test_client()
    first, q = start_login(client)
    before = sid_cookie(first)
    assert before
    resp, _ = finish_login(client, fake_idp, q)
    after = sid_cookie(resp)
    assert after
    for header in (before, after):
        assert "Secure" in header
        assert "HttpOnly" in header
        assert "SameSite=Lax" in header
    assert before.split(";")[0] != after.split(";")[0]


def test_no_token_reaches_the_browser(make_app, fake_idp):
    client = make_app().test_client()
    responses = []
    first, q = start_login(client)
    responses.append(first)
    resp, tokens = finish_login(client, fake_idp, q)
    responses.append(resp)
    responses.append(client.get("/whoami", base_url=HTTPS))
    secrets = [tokens["id_token"], tokens["access_token"], tokens["refresh_token"]]
    for r in responses:
        blob = str(r.headers) + r.get_data(as_text=True)
        for secret in secrets:
            assert secret not in blob


def test_signed_in_login_visit_forwards_without_idp(make_app, fake_idp, idp_mock):
    client = make_app().test_client()
    _, q = start_login(client)
    finish_login(client, fake_idp, q)
    calls_before = len(idp_mock.calls)
    resp = client.get("/auth/login", base_url=HTTPS)
    assert resp.status_code == 303
    assert resp.headers["Location"] == "/"
    assert len(idp_mock.calls) == calls_before


def test_replayed_callback_lands_on_login(make_app, fake_idp):
    client = make_app().test_client()
    _, q = start_login(client)
    url = f"/auth/callback?code=abc&state={q['state']}"
    finish_login(client, fake_idp, q)
    resp = client.get(url, base_url=HTTPS)
    assert resp.status_code < 500
    assert resp.status_code in (302, 303)
    assert resp.headers["Location"] == "/auth/login"


def test_bad_id_token_never_signs_in(make_app, fake_idp):
    client = make_app().test_client()
    _, q = start_login(client)
    other = RSAKey.generate_key(2048, {"kid": fake_idp.kid, "use": "sig", "alg": "RS256"})
    forged = fake_idp.id_token(nonce=q["nonce"], signer=other)
    resp, _ = finish_login(client, fake_idp, q, id_token=forged)
    assert resp.status_code in (302, 303)
    assert resp.headers["Location"] == "/auth/login"
    assert client.get("/whoami", base_url=HTTPS).get_json()["claims"] is None


def test_prefix_mount_scopes_cookie_and_return_path(make_app, fake_idp, config):
    cfg = AuthConfig(
        providers=("google",),
        user_pool_id=config.user_pool_id,
        client_id=config.client_id,
        cognito_domain=config.cognito_domain,
        base_url="https://x.example.com/dash",
        session_backend="memory",
    )
    client = make_app(cfg).test_client()
    base = "https://x.example.com/dash"
    first, q = start_login(client, base_url=base)
    assert "Path=/dash" in sid_cookie(first)
    assert q["redirect_uri"] == "https://x.example.com/dash/auth/callback"

    client.get("/seed?to=/other", base_url=base)
    _, q = start_login(client, base_url=base)
    resp, _ = finish_login(client, fake_idp, q, base_url=base)
    assert resp.status_code == 303
    assert resp.headers["Location"] == "/dash/"
