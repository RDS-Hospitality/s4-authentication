from __future__ import annotations

import os
from dataclasses import dataclass, fields
from datetime import timedelta
from typing import Any, Literal, Mapping
from urllib.parse import urlencode

BASELINE_SCOPES = ("openid", "email", "profile")
_IDP_NAMES = {"google": "Google", "microsoft": "Microsoft"}
_LOCAL_HTTP = ("http://localhost", "http://127.0.0.1")
_REQUIRED = ("providers", "user_pool_id", "client_id", "cognito_domain", "base_url")
_TUPLE_FIELDS = ("providers", "scopes", "graphql_urls")
_MINUTE_FIELDS = {"access_ttl", "refresh_ttl", "idle_timeout"}


def _is_local_http(url: str) -> bool:
    for prefix in _LOCAL_HTTP:
        if url == prefix or url.startswith((prefix + ":", prefix + "/")):
            return True
    return False


@dataclass(frozen=True)
class AuthConfig:
    providers: tuple[str, ...]
    user_pool_id: str
    client_id: str
    cognito_domain: str
    base_url: str
    scopes: tuple[str, ...] = BASELINE_SCOPES
    post_login_route: str = "/"
    access_ttl: timedelta = timedelta(minutes=60)
    refresh_ttl: timedelta = timedelta(days=1)
    idle_timeout: timedelta = timedelta(minutes=30)
    graphql_urls: tuple[str, ...] = ()
    role_claim: str = "hasura_allowed_roles"
    default_role_claim: str = "hasura_default_role"
    session_backend: Literal["dynamodb", "memory"] = "dynamodb"
    session_table: str = "s4-auth-sessions"
    cookie_name: str = "s4_session"

    def __post_init__(self) -> None:
        if not self.providers:
            raise ValueError("providers must not be empty")
        unknown = [p for p in self.providers if p not in _IDP_NAMES]
        if unknown:
            raise ValueError(f"unknown providers: {unknown}; allowed: google, microsoft")
        route = self.post_login_route
        if not route.startswith("/") or route.startswith("//"):
            raise ValueError("post_login_route must start with a single '/'")
        if not (self.base_url.startswith("https://") or _is_local_http(self.base_url)):
            raise ValueError("base_url must be https:// (http only for localhost/127.0.0.1)")
        missing = [s for s in BASELINE_SCOPES if s not in self.scopes]
        if missing:
            raise ValueError(f"scopes missing baseline scopes: {missing}")
        for name in _MINUTE_FIELDS:
            if getattr(self, name) <= timedelta(0):
                raise ValueError(f"{name} must be positive")
        if self.session_backend not in ("dynamodb", "memory"):
            raise ValueError("session_backend must be 'dynamodb' or 'memory'")

    @property
    def region(self) -> str:
        return self.user_pool_id.split("_", 1)[0]

    @property
    def issuer(self) -> str:
        return f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"

    @property
    def metadata_url(self) -> str:
        return f"{self.issuer}/.well-known/openid-configuration"

    @property
    def callback_url(self) -> str:
        return f"{self.base_url}/auth/callback"

    @property
    def revoke_url(self) -> str:
        return f"https://{self.cognito_domain}/oauth2/revoke"

    @property
    def logout_url(self) -> str:
        query = urlencode(
            {"client_id": self.client_id, "logout_uri": f"{self.base_url}/auth/signed-out"}
        )
        return f"https://{self.cognito_domain}/logout?{query}"

    @property
    def identity_provider(self) -> str | None:
        if len(self.providers) == 1:
            return _IDP_NAMES[self.providers[0]]
        return None

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> AuthConfig:
        known = {f.name for f in fields(cls)}
        unknown = set(m) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        missing = [k for k in _REQUIRED if k not in m]
        if missing:
            raise ValueError(f"missing required config: {missing}")
        values: dict[str, Any] = {}
        for key, value in m.items():
            if key in _TUPLE_FIELDS:
                if isinstance(value, str):
                    value = [v.strip() for v in value.split(",") if v.strip()]
                value = tuple(value)
            elif key in _MINUTE_FIELDS and not isinstance(value, timedelta):
                value = timedelta(minutes=float(value))
            values[key] = value
        return cls(**values)

    @classmethod
    def from_env(
        cls, prefix: str = "S4_AUTH_", environ: Mapping[str, str] | None = None
    ) -> AuthConfig:
        env = os.environ if environ is None else environ
        found = {}
        for f in fields(cls):
            raw = env.get(prefix + f.name.upper())
            if raw is not None and raw != "":
                found[f.name] = raw
        return cls.from_mapping(found)
