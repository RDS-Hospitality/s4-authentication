from __future__ import annotations

import time

from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from s4_auth_flask.config import AuthConfig

# Cognito signs with RS256 only; an explicit allowlist also rules out alg "none" and HS* confusion.
_ALGORITHMS = ["RS256"]


class TokenInvalid(Exception):
    pass


def verify_id_token(
    id_token: str, *, config: AuthConfig, jwks: dict, now: float | None = None
) -> dict:
    try:
        decoded = jwt.decode(id_token, KeySet.import_key_set(jwks), algorithms=_ALGORITHMS)
    except (JoseError, ValueError, KeyError, TypeError) as exc:
        raise TokenInvalid(f"signature or format invalid: {exc}") from exc

    claims = decoded.claims
    if claims.get("iss") != config.issuer:
        raise TokenInvalid("issuer mismatch")
    aud = claims.get("aud")
    if aud != config.client_id:
        raise TokenInvalid("audience mismatch")
    if claims.get("token_use") != "id":
        raise TokenInvalid("not an id token")
    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        raise TokenInvalid("missing exp")
    if exp <= (time.time() if now is None else now):
        raise TokenInvalid("token expired")
    return dict(claims)
