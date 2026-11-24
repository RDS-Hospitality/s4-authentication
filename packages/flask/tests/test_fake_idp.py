import requests

from s4_auth_flask.tokens import verify_id_token


def test_install_serves_metadata_jwks_token_and_revoke(fake_idp, idp_mock, config):
    meta = requests.get(config.metadata_url).json()
    assert meta["issuer"] == config.issuer
    jwks = requests.get(meta["jwks_uri"]).json()
    assert jwks["keys"][0]["kid"] == "test-key"
    assert "d" not in jwks["keys"][0]
    verify_id_token(fake_idp.id_token(), config=config, jwks=jwks)

    fake_idp.set_token_reply({"id_token": "x"})
    resp = requests.post(meta["token_endpoint"], data={"a": "b"})
    assert resp.json() == {"id_token": "x"}
    assert requests.post(config.revoke_url, data={"token": "t"}).status_code == 200
    assert len(fake_idp.token_requests) == 1 and len(fake_idp.revoke_requests) == 1
