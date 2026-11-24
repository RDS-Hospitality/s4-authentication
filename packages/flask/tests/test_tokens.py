import base64
import json
import time

import pytest
from joserfc.jwk import RSAKey

from s4_auth_flask.tokens import TokenInvalid, verify_id_token


def verify(idp, config, token, **kw):
    return verify_id_token(token, config=config, jwks=idp.jwks(), **kw)


def test_valid_token_returns_claims(fake_idp, config):
    claims = verify(fake_idp, config, fake_idp.id_token(email="a@b.c"))
    assert claims["email"] == "a@b.c"
    assert claims["iss"] == config.issuer


def test_wrong_key_rejected(fake_idp, config):
    other = RSAKey.generate_key(2048, {"kid": "test-key"})
    with pytest.raises(TokenInvalid):
        verify(fake_idp, config, fake_idp.id_token(signer=other))


def test_wrong_aud_rejected(fake_idp, config):
    with pytest.raises(TokenInvalid):
        verify(fake_idp, config, fake_idp.id_token(aud="someone-else"))


def test_wrong_iss_rejected(fake_idp, config):
    with pytest.raises(TokenInvalid):
        verify(fake_idp, config, fake_idp.id_token(iss="https://evil.example"))


def test_expired_rejected(fake_idp, config):
    with pytest.raises(TokenInvalid):
        verify(fake_idp, config, fake_idp.id_token(exp=int(time.time()) - 10))


def test_missing_exp_rejected(fake_idp, config):
    with pytest.raises(TokenInvalid):
        verify(fake_idp, config, fake_idp.id_token(exp=None))


def test_now_parameter_controls_expiry(fake_idp, config):
    token = fake_idp.id_token(exp=1000)
    assert verify(fake_idp, config, token, now=999)["exp"] == 1000
    with pytest.raises(TokenInvalid):
        verify(fake_idp, config, token, now=1000)


def test_access_token_rejected(fake_idp, config):
    with pytest.raises(TokenInvalid):
        verify(fake_idp, config, fake_idp.id_token(token_use="access"))


def test_unknown_kid_rejected(fake_idp, config):
    with pytest.raises(TokenInvalid):
        verify(fake_idp, config, fake_idp.id_token(kid="other-kid"))


def _b64(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def test_alg_none_rejected(fake_idp, config):
    payload = {
        "iss": config.issuer, "aud": config.client_id, "token_use": "id",
        "exp": int(time.time()) + 3600,
    }
    token = f"{_b64({'alg': 'none', 'kid': 'test-key'})}.{_b64(payload)}."
    with pytest.raises(TokenInvalid):
        verify(fake_idp, config, token)


def test_garbage_rejected(fake_idp, config):
    with pytest.raises(TokenInvalid):
        verify(fake_idp, config, "not-a-jwt")
