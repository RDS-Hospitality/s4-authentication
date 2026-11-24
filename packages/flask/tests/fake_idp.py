from __future__ import annotations

import json
import time
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc import jwt
from joserfc.jwk import RSAKey

from s4_auth_flask.config import AuthConfig

KID = "test-key"


class FakeIdP:
    """Stands in for Cognito: signs tokens and serves metadata, JWKS, token and revoke endpoints."""

    def __init__(self, config: AuthConfig, kid: str = KID) -> None:
        self.config = config
        self.kid = kid
        self.key = RSAKey.generate_key(2048, {"kid": kid, "use": "sig", "alg": "RS256"})
        self.token_reply: Callable[[Any], tuple[int, dict]] | None = None
        self.token_requests: list[Any] = []
        self.revoke_requests: list[Any] = []

    def jwks(self) -> dict:
        return {"keys": [self.key.as_dict(private=False)]}

    def _sign(self, claims: dict, key: RSAKey | None = None, kid: str | None = None) -> str:
        header = {"alg": "RS256", "kid": kid or self.kid}
        return jwt.encode(header, claims, key or self.key)

    def id_token(self, *, signer: RSAKey | None = None, kid: str | None = None, **claims: Any) -> str:
        base = {
            "iss": self.config.issuer,
            "aud": self.config.client_id,
            "token_use": "id",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "email": "user@example.com",
            "sub": "sub-123",
        }
        base.update(claims)
        return self._sign({k: v for k, v in base.items() if v is not None}, signer, kid)

    def access_token(self, *, signer: RSAKey | None = None, kid: str | None = None, **claims: Any) -> str:
        base = {
            "iss": self.config.issuer,
            "client_id": self.config.client_id,
            "token_use": "access",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "sub": "sub-123",
        }
        base.update(claims)
        return self._sign({k: v for k, v in base.items() if v is not None}, signer, kid)

    def set_token_reply(self, reply: Callable[[Any], tuple[int, dict]] | dict, status: int = 200) -> None:
        """Set the token endpoint reply: a JSON body, or a callable(request) -> (status, body)."""
        self.token_reply = reply if callable(reply) else (lambda _req: (status, reply))

    def install(self, responses_mock: Any, config: AuthConfig | None = None) -> None:
        config = config or self.config
        domain = config.cognito_domain
        metadata = {
            "issuer": config.issuer,
            "authorization_endpoint": f"https://{domain}/oauth2/authorize",
            "token_endpoint": f"https://{domain}/oauth2/token",
            "jwks_uri": f"{config.issuer}/.well-known/jwks.json",
        }
        responses_mock.add(responses_mock.GET, config.metadata_url, json=metadata)
        responses_mock.add(responses_mock.GET, metadata["jwks_uri"], json=self.jwks())

        def token_cb(request):
            self.token_requests.append(request)
            if self.token_reply is None:
                return (500, {}, json.dumps({"error": "no token reply configured"}))
            status, body = self.token_reply(request)
            return (status, {"Content-Type": "application/json"}, json.dumps(body))

        def revoke_cb(request):
            self.revoke_requests.append(request)
            return (200, {}, "")

        responses_mock.add_callback(
            responses_mock.POST, metadata["token_endpoint"], callback=token_cb
        )
        responses_mock.add_callback(responses_mock.POST, config.revoke_url, callback=revoke_cb)
