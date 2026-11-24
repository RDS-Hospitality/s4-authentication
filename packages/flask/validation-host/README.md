# Validation host

A small Flask app that runs `s4_auth_flask` against a real Cognito pool, so a person can perform the behavioural (eye-icon) checks in `docs/CONFORMANCE.md`. It is a test tool: it is not part of the published `flask` package and creates no AWS resources.

Routes:

| Route | Guard | Shows |
|-------|-------|-------|
| `/` | `@public` | Link to sign in |
| `/protected` | any signed-in user | Email, roles, session-cookie name (never a token), a logout form, a `POST /echo` form |
| `/admin` | `@require_role("s4-auth-validation")` | Confirmation text |
| `POST /echo` | any signed-in user | Confirmation text |

## AWS steps (you do these)

1. **Test app client** on the pool: identity provider Google, authorization code flow, no client secret, scopes `openid email profile`, callback URL `http://localhost:5050/auth/callback`, sign-out URL `http://localhost:5050/`.
2. **Domain-gate allowlist:** add the new client id to the pool's allowlist. On the fleet pool that is the `DOMAIN_GATE_ALLOWLIST` environment variable of the domain-gate Lambda. Without it, sign-in is refused.
3. **Optional, for `/admin`:** create a Cognito group named `s4-auth-validation`, add yourself to it, and add the client id to the role Lambda's claims-emission set. Without this `/admin` returns 403.

## Install and run

Python 3.11 or newer. From `packages/flask/validation-host`:

```bash
uv venv
uv pip install -e ..
cp .env.example .env     # fill in pool id, client id, Cognito domain
set -a; source .env; set +a
uv run flask --app app run --port 5050
```

Open `http://localhost:5050/`. Cookies are `Secure`; browsers treat `http://localhost` as a secure context, so they are stored and sent there. Use `localhost`, not another hostname. The host uses the in-memory session backend (one process; do not run with reloader or multiple workers, and restarting it drops every session).

`S4_AUTH_IDLE_TIMEOUT` (minutes) exists in `.env.example` for the S3.1 check only. It is a validation setting for this host; the adapter's default stays 30.

## Checklist

Quoted pass conditions are from `docs/CONFORMANCE.md`. Use a private window with devtools open (Network tab, "Preserve log" on).

- [ ] **C1.2** Authorization redirect uses `response_type=code` and includes `code_challenge` + `code_challenge_method=S256`. Click Sign in; inspect the redirect to the Cognito `/authorize` URL.
- [ ] **C3.3** A session left idle 30 min is logged out; under active use the hour boundary refreshes silently (no surprise re-login). Leave default idle (unset the override); idle 30+ minutes, then load `/protected` and expect the login redirect. In a second session, keep clicking `/protected` past the 60-minute mark and expect no login redirect.
- [ ] **C4.2** After logout: local token storage empty and a protected route demands full re-auth (no silent re-entry). Log out, check Application > Storage holds no tokens, then open `/protected`: the Cognito sign-in is demanded again.
- [ ] **C5.1** After login, Back does not return to / re-fire the OAuth callback (callback URL replaced out of history).
- [ ] **C5.2** While logged out, Back from a protected page lands on login, with no protected-content flash and no callback re-fire.
- [ ] **C5.3** While logged in, navigating to the login route (`/auth/login`) forwards (to the pending return URL if present, else the post-login route) without re-initiating the auth flow: no authorization request in the network log, no auth-flow error in the console.
- [ ] **S2.1** No token appears in any `Set-Cookie` header or response body, across sign-in, an authenticated page, and logout. Search each response in the Network tab for the ID, access and refresh token values.
- [ ] **S2.2** The session cookie carries `Secure`, `HttpOnly` and `SameSite=Lax` or `Strict` (devtools Application tab, or `curl -i` on the callback response). The cookie value after sign-in differs from the value before it.
- [ ] **S3.1** Idle for longer than `session.idleTimeout`, then request a protected page: full re-authentication is demanded. Set `S4_AUTH_IDLE_TIMEOUT=2`, restart the host, sign in, wait over 2 minutes, load `/protected`. Unset it afterwards.
- [ ] **S3.2** With the access token expired and the refresh token still valid, the next request succeeds without a login redirect. Set `S4_AUTH_ACCESS_TTL=1` (minutes) and keep the idle timeout above the wait; sign in, wait over a minute, reload `/protected`. (This overrides the host's expiry clock only; the real client still issues 60-minute tokens.)
- [ ] **S4.1** After logout, replaying the old session identifier is rejected, and a protected page demands full re-authentication. Copy the `s4_session` cookie value, log out, put the old value back (devtools or `curl -H "Cookie: s4_session=..."`), and request `/protected`.
- [ ] **S5.1** The callback is answered by a 3xx redirect, never a 200 with a body. In the Network tab the `/auth/callback` response is 303; `curl -i` on the callback URL is also not a 200.
- [ ] **S7.1** A POST sent on an expired session returns 401, and the request is not replayed or stored as `returnUrl` after the user signs in. Sign in, expire the session (S3.1 setting, or delete the cookie server-side by restarting the host), press `POST /echo`: expect 401; then sign in and confirm you land on the post-login route, not on a replayed `/echo`.
