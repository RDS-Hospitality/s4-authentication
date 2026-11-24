from dataclasses import fields
from datetime import timedelta

import pytest

from s4_auth_flask.config import AuthConfig

POOL = "us-east-1_EXAMPLE01"
DOMAIN = "example-auth.auth.us-east-1.amazoncognito.com"


def make(**over):
    base = dict(
        providers=("google",),
        user_pool_id=POOL,
        client_id="abc",
        cognito_domain=DOMAIN,
        base_url="https://dash.example.com",
    )
    base.update(over)
    return AuthConfig(**base)


def test_defaults_match_the_contract():
    c = make()
    assert c.scopes == ("openid", "email", "profile")
    assert c.access_ttl == timedelta(minutes=60)
    assert c.refresh_ttl == timedelta(days=1)
    assert c.idle_timeout == timedelta(minutes=30)
    assert c.role_claim == "hasura_allowed_roles"
    assert c.default_role_claim == "hasura_default_role"
    assert c.post_login_route == "/"
    assert c.session_backend == "dynamodb"
    assert c.session_table == "s4-auth-sessions"
    assert c.cookie_name == "s4_session"
    assert c.graphql_urls == ()


def test_derived_urls():
    c = make()
    assert c.region == "us-east-1"
    assert c.issuer == f"https://cognito-idp.us-east-1.amazonaws.com/{POOL}"
    assert c.metadata_url == c.issuer + "/.well-known/openid-configuration"
    assert c.callback_url == "https://dash.example.com/auth/callback"
    assert c.revoke_url == f"https://{DOMAIN}/oauth2/revoke"
    assert c.logout_url == (
        f"https://{DOMAIN}/logout?client_id=abc"
        "&logout_uri=https%3A%2F%2Fdash.example.com%2F"
    )


def test_single_provider_names_the_idp():
    assert make(providers=("google",)).identity_provider == "Google"
    assert make(providers=("microsoft",)).identity_provider == "Microsoft"
    assert make(providers=("google", "microsoft")).identity_provider is None


@pytest.mark.parametrize(
    "over",
    [
        {"providers": ("github",)},
        {"providers": ()},
        {"post_login_route": "dash"},
        {"post_login_route": "//evil.example.com"},
        {"base_url": "http://dash.example.com"},
        {"scopes": ("openid", "email")},
        {"access_ttl": timedelta(0)},
        {"refresh_ttl": timedelta(minutes=-1)},
        {"idle_timeout": timedelta(0)},
    ],
)
def test_rejects_bad_values(over):
    with pytest.raises(ValueError):
        make(**over)


@pytest.mark.parametrize(
    "url", ["http://localhost", "http://localhost:5000", "http://127.0.0.1:8000"]
)
def test_allows_local_http(url):
    assert make(base_url=url).base_url == url


def test_from_env_reads_prefixed_vars():
    env = {
        "S4_AUTH_PROVIDERS": "google,microsoft",
        "S4_AUTH_USER_POOL_ID": POOL,
        "S4_AUTH_CLIENT_ID": "abc",
        "S4_AUTH_COGNITO_DOMAIN": DOMAIN,
        "S4_AUTH_BASE_URL": "https://dash.example.com",
        "S4_AUTH_GRAPHQL_URLS": "https://a.example.com/v1/graphql, https://b.example.com/v1/graphql",
    }
    c = AuthConfig.from_env(environ=env)
    assert c.providers == ("google", "microsoft")
    assert c.graphql_urls == (
        "https://a.example.com/v1/graphql",
        "https://b.example.com/v1/graphql",
    )


def test_from_env_reads_os_environ(monkeypatch):
    monkeypatch.setenv("X_PROVIDERS", "google")
    monkeypatch.setenv("X_USER_POOL_ID", POOL)
    monkeypatch.setenv("X_CLIENT_ID", "abc")
    monkeypatch.setenv("X_COGNITO_DOMAIN", DOMAIN)
    monkeypatch.setenv("X_BASE_URL", "https://dash.example.com")
    assert AuthConfig.from_env("X_").client_id == "abc"


def test_from_mapping_coerces_lists_and_minutes():
    c = AuthConfig.from_mapping(
        dict(
            providers=["google"],
            user_pool_id=POOL,
            client_id="abc",
            cognito_domain=DOMAIN,
            base_url="https://dash.example.com",
            graphql_urls=["https://a/v1/graphql"],
        )
    )
    assert c.providers == ("google",)
    assert c.graphql_urls == ("https://a/v1/graphql",)


def test_no_field_can_disable_guards():
    banned = ("disable", "bypass", "skip", "insecure", "guard")
    names = [f.name for f in fields(AuthConfig)]
    assert not [n for n in names if any(b in n for b in banned)]
    assert "client_secret" not in names
