# s4-auth-flask

Standardized S4 authentication for **Flask** apps. Sign-in is Cognito (Google) with the
authorization code flow and PKCE (S256), as a public client with no client secret. The server
keeps the tokens; the browser holds only an opaque session cookie. This is the server-session
realization of the contract in [`STANDARD.md`](./STANDARD.md) (see its "Server-session profile").

Every route is **denied unless the user is signed in**. A view opts out with `@public`. No
setting turns the guard off.

## Install

Pin a release tag. An auth boundary should be reproducible.

```bash
pip install "git+https://github.com/RDS-Hospitality/s4-authentication.git@flask-vX.Y.Z"

# with the DynamoDB session store (boto3 and mypy-boto3-dynamodb, which Flask-Session
# imports at runtime):
pip install "s4-auth-flask[dynamodb] @ git+https://github.com/RDS-Hospitality/s4-authentication.git@flask-vX.Y.Z"
```

Python 3.11 or newer. Run on a **UTC host** (Lambda is UTC): Flask-Session computes the
DynamoDB `expiration` value from a naive UTC clock.

## Integrate

```python
import boto3
from flask import Flask
from s4_auth_flask import AuthConfig, S4Auth, current_user, public, require_role

app = Flask(__name__)
S4Auth(app, AuthConfig.from_env(), session_resource=boto3.resource("dynamodb"))

@public
@app.get("/health")
def health():
    return "ok"

@app.get("/")
def home():
    return f"Hello {current_user()['email']}"

@app.get("/admin")
@require_role("admin")
def admin():
    return "admins only"
```

`session_resource` is required with the default `dynamodb` session backend. Omit it only
with `S4_AUTH_SESSION_BACKEND=memory`.

The adapter registers three routes under `/auth`:

| Route | Does |
|-------|------|
| `GET /auth/login` | Starts sign-in (redirects to Cognito). Goes straight to the landing page if already signed in. |
| `GET /auth/callback` | Completes sign-in, verifies the ID token, issues a fresh session id, redirects (303). A stale or replayed callback redirects back to login; an IdP refusal shows a 401 page with the reason; an IdP outage shows a 503 page. |
| `POST /auth/logout` | Revokes the refresh token, deletes the server session, expires the cookie, redirects to Cognito's logout. |
| `GET /auth/signed-out` | Where Cognito's logout lands: "You are signed out." with a sign-in link. Public; never redirects. |

## Configuration

`AuthConfig.from_env(prefix="S4_AUTH_")` reads one variable per field, named
`<prefix><FIELD>` in upper case. Unset or empty variables take the default. Unknown
fields and invalid values raise `ValueError` at startup. `AuthConfig.from_mapping(dict)` takes
the same fields.

| Variable | Required | Default | Meaning |
|----------|:--------:|---------|---------|
| `S4_AUTH_PROVIDERS` | yes | | Comma-separated: `google`, `microsoft`. With exactly one, login goes straight to that provider. |
| `S4_AUTH_USER_POOL_ID` | yes | | e.g. `us-east-1_AbCdEfGhI`. The region and issuer derive from it. |
| `S4_AUTH_CLIENT_ID` | yes | | The app client id. |
| `S4_AUTH_COGNITO_DOMAIN` | yes | | Bare host of the pool's hosted-UI domain, no scheme. |
| `S4_AUTH_BASE_URL` | yes | | Public URL of the app, including any mount path. `https://` only (`http://localhost` and `http://127.0.0.1` are allowed for local runs). |
| `S4_AUTH_SCOPES` | | `openid,email,profile` | Comma-separated. Must include the three defaults. |
| `S4_AUTH_POST_LOGIN_ROUTE` | | `/` | Landing page when there is no return path. Must start with a single `/`. |
| `S4_AUTH_ACCESS_TTL` | | 60 | Minutes. Mirrors the app client's access-token validity. |
| `S4_AUTH_REFRESH_TTL` | | 1 day | Minutes. Mirrors the app client's refresh-token validity; also the cookie lifetime. |
| `S4_AUTH_IDLE_TIMEOUT` | | 30 | Minutes without a request before the server ends the session. |
| `S4_AUTH_GRAPHQL_URLS` | | none | Comma-separated data-layer URLs that `auth_headers()` may attach the token to. |
| `S4_AUTH_ROLE_CLAIM` | | `hasura_allowed_roles` | ID-token claim holding the user's roles. |
| `S4_AUTH_DEFAULT_ROLE_CLAIM` | | `hasura_default_role` | ID-token claim holding the default role. Accepted for parity with the other adapters; no guard reads it yet. |
| `S4_AUTH_SESSION_BACKEND` | | `dynamodb` | `dynamodb`, or `memory` (one process only; development). |
| `S4_AUTH_SESSION_TABLE` | | `s4-auth-sessions` | DynamoDB table name. |
| `S4_AUTH_COOKIE_NAME` | | `s4_session` | Session cookie name. |

The cookie is always `Secure`, `HttpOnly`, `SameSite=Lax`.

## Using the guards

- `@public` exempts a view. Put it above the route decorator, as in the example.
- `@require_role("admin")` or `@require_role(["admin", "editor"])` allows a user holding any
  listed role, otherwise 403. An empty requirement raises `ValueError` when the view is defined.
- `has_role(...)` is the same test as a function, for use inside a view.
- `current_user()` returns the verified ID-token claims plus `roles`, or `None`.
- `auth_headers(url)` returns `{"Authorization": "Bearer <ID token>"}` only when `url` matches
  an entry in `S4_AUTH_GRAPHQL_URLS`, otherwise `{}`. An entry is an absolute URL (origin plus
  optional path prefix) or a path prefix starting with `/` (matched against the app's own
  origin).

### What a denied request gets

- A **GET that accepts HTML** is redirected to `/auth/login`, and the user returns to the page
  afterwards (only same-site paths are honoured).
- Any other request (POST, JSON, and so on) gets **401** and is never replayed after sign-in.
- A signed-in user idle past the timeout, or whose refresh token Cognito refuses, is signed
  out and then treated as above.
- Logout accepts **POST only**, and only when `Origin` (or `Referer`) matches `base_url`;
  otherwise 403. Use a form button, not a link.
- **Session-store outage:** requests are denied, logout returns **503**, and a failed save of
  the session returns **500**. The adapter fails closed.

## Session table

The adapter never creates the table or enables TTL. Create it yourself:

| Setting | Value |
|---------|-------|
| Partition key | `id` (String) |
| TTL attribute | `expiration` (TTL enabled) |

The same values are in `s4_auth_flask.extension.DYNAMODB_TABLE_SHAPE`
(`partition_key: "id"`, `key_type: "S"`, `ttl_attribute: "expiration"`, `ttl_enabled: True`).

TTL is housekeeping only, so expired rows eventually disappear. Session lifetime is enforced
by the adapter (idle timeout) and by Cognito refusing the refresh token after its lifetime.
The app's role needs `dynamodb:GetItem`, `UpdateItem` and `DeleteItem` on the table.

## AWS setup per app

The operator does these steps. The adapter never creates AWS resources.

1. **App client** on the user pool:
   - Identity provider: Google. Flow: authorization code. **No client secret.**
   - Scopes: `openid`, `email`, `profile`.
   - Token validity: access 60 minutes, ID 60 minutes, refresh 1 day.
   - Callback URL: `{base_url}/auth/callback`. Sign-out URL: `{base_url}/auth/signed-out`.
2. **Domain-gate allowlist.** Add the new client id to the pool's inbound-federation
   domain-gate allowlist. On the fleet pool this is the `DOMAIN_GATE_ALLOWLIST` of the
   domain-gate Lambda. **Without it, sign-in is refused.**
3. **Roles (only if the app uses them).** Add the client id to the role Lambda's
   claims-emission set, and create a Cognito group for each role. Until the client is in the
   emission set, the token has no role claim and the adapter logs a warning once.
4. **Session table**, as above.

## Tests

From `packages/flask/`:

```bash
uv run --extra test pytest -q
```
