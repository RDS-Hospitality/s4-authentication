<!--
  THE PORT — normative, stack-agnostic layer.

  This file MUST NOT name a specific framework, library, or framework-specific
  API (no "Amplify", no "Angular", no `replaceUrl`, no `atob`-as-mechanism).
  State the *observable outcome* + a *mechanical conformance test*. The *how*
  belongs in a per-stack adapter.

  The one place a downstream product's identifier may appear is as a DEFAULT
  VALUE in the Config Vocabulary table (the fleet's role-claim names) — never
  in a clause's Rule. A clause describes the credential and the claim; the
  vocabulary binds the fleet's current names for them.
-->

# The Auth Contract (`STANDARD.md`)

- **Status:** normative — the source of truth for S4 authentication.
- **Layer:** the *port* (Ports & Adapters). Implementations conform to this; this
  conforms to no implementation.

An application is **conformant** when every clause below holds, demonstrated by
its conformance test. Each clause exists to fix a real divergence found across
the S4 frontend repos. The nine clauses are numbered **C1–C9**; the `(C#)` tag
after each heading is that clause's stable identifier — used by conformance
tests and by cross-references between clauses.

> **How to read a clause.** *Rule* = the observable outcome you must achieve.
> *Why* = the rationale + the divergence it fixes. *Conformance test* = a
> mechanical check, stack-agnostic. *How you achieve it in a given stack* is the
> adapter's job, not this document's.

---

## OAuth flow: Authorization Code + PKCE (S256) (C1)

**Rule.** Tokens are obtained via the OAuth 2.0 **Authorization Code** flow with
**PKCE**, challenge method **S256**. The **implicit** flow
(`response_type=token`) is **prohibited**.

**Why.** OAuth 2.1 / RFC 7636. Implicit exposes tokens in the URL and browser
history; PKCE prevents authorization-code interception.

**Conformance test.**
- Every authorization request to the IdP uses `response_type=code`; **none** uses
  `response_type=token`.
- The authorization request carries `code_challenge` and
  `code_challenge_method=S256`.
- *(Observable at the network/redirect layer; independent of how the client
  constructs the request.)*

---

## Token storage & validation (C2)

**Rule.** Access/ID/refresh tokens are held in browser web storage — **`localStorage`
is the fleet default** (persistent session: survives reload and is shared across tabs,
the behavior users expect); `sessionStorage` is acceptable where the session should not
outlive the tab; **nothing weaker than `localStorage`**.
Any **trust or authorization decision** is made only on a token **verified
against the issuer's JWKS** (signature valid; `iss`, `aud`, `exp` checked). A
raw, unverified decode of a token MUST NOT drive a trust decision.

**Why.** IETF *OAuth for Browser-Based Apps* BCP flags browser web storage as the
weakest accepted model and `localStorage` as its most-exposed point; the fleet accepts
`localStorage` as the floor — a deliberate trade for a persistent, multi-tab session,
bounded by short token TTLs (C3) and the JWKS-validation requirement below. A
`Secure`+`HttpOnly`+`SameSite` cookie via a BFF is the hardened option where needed.
OIDC Core — trust requires signature verification.

**Conformance test.**
- No code path reaches an authenticated/authorized state from an **unverified**
  token decode. (A decode used purely for non-trust display is permitted.)
- Token verification resolves the issuer's JWKS and checks signature + `iss` +
  `aud` + `exp`.
- Tokens are never written to a cookie without `Secure`+`HttpOnly`+`SameSite`,
  nor to any store more exposed than `localStorage`.

---

## Session lifetime (C3)

**Rule.**
- Access & ID token TTL = **60 minutes**. While the refresh token is still
  valid, an expired access token is renewed **without forcing the user to
  re-authenticate** (a silent refresh). Whether that renewal is on-demand or
  scheduled ahead of expiry is the adapter's choice — it is not required to be a
  proactive scheduler.
- Refresh token TTL = **1 day** (24 h) — the **default**. A product with a
  business reason for a longer working session raises it **deliberately** (an
  app-client config change, e.g. a console edit), recorded as a sanctioned
  deviation. A single default, tuned per product when justified — not a value
  baked per-app into code.
- **Idle timeout = 30 minutes**: 30 minutes without user activity triggers a
  logout (per C4). This is **enforced client-side** — no IdP/app-client field
  expresses an idle timeout, so it lives in the adapter, not the Cognito config.

**Why.** With browser-stored tokens, lifetime is the primary security knob: a
60-minute access token bounds blast radius to ~1 hour while silent refresh avoids
forcing a re-login at the hour boundary. A **1-day refresh window** is the default
session length — tight enough to bound exposure for external users, with a
deliberate per-product opt-up where a longer working session is justified. A
30-minute idle timeout protects unattended sessions. OWASP Session Management.

**Conformance test.**
- IdP app-client config: access-token validity = 60 min, ID-token validity =
  60 min, refresh-token validity = **1 day** (unless a longer window is recorded
  as a sanctioned deviation). *(Inspectable in the Cognito app-client — the
  **console** for an existing pool, the CFN template for a new one; see
  `infra/cognito/`.)*
- A session whose refresh token is still valid does **not** force a re-login when
  the access token expires (renewal is silent; no user-visible re-login at the
  hour boundary under normal use).
- 30 minutes of inactivity ends the session (client-side idle logout — the
  app-client config alone cannot demonstrate this clause).

---

## Logout is complete (C4)

**Rule.** A logout performs **all three**:
1. **Global** session revocation at the provider (not a local-only sign-out).
2. **Clears all locally stored** tokens and session state.
3. **Redirects through the Cognito `/logout` endpoint** so the IdP session ends.

A "logout" that leaves the user able to silently re-enter is **non-conformant**.
**No stub logouts.**

**Why.** OIDC RP-Initiated Logout. A local-only sign-out that leaves the IdP
session intact lets the user silently re-enter — the failure this fixes.

**Conformance test.**
- After logout: local token storage is **empty**, **and** accessing a protected
  route requires a **full re-authentication** (no silent token re-acquisition).
- No logout handler is a no-op / stub.

---

## Callback history & back-button (C5)

**Rule.** Once the OAuth callback (carrying `code`/`state`) is consumed, its URL
is **removed from session history**, so pressing **Back** does not re-fire the
callback. Pressing **Back from a protected page while logged out** lands on the
**login page** — never a re-firing callback, never a flash of protected content.

**Rule (login idempotence).** While authenticated, a visit to the login route
**forwards** — to the pending `returnUrl` if one exists (C6's recovery value),
else the configured post-login route — **without re-initiating the auth flow
and without stacking a history entry** (the login entry is replaced, so Back
from the destination skips it). A login page that re-runs sign-in, throws, or
stacks history on an authenticated revisit is non-conformant.

**App-origin history outcome.** After a completed login, app-origin history
satisfies: *(a)* the consumed callback entry is never present; *(b)* the login
entry is replaced on forward, never stacked. The concrete entry list is
adapter-specific — in particular, a **deep-link entry** (login forced by a
guard from a protected URL) legitimately leaves the deep-linked URL in history
beneath the login entry; Back to it simply re-runs the guard.

**The external residual (named, bounded).** The full-page redirect flow leaves
**IdP pages on external origins in the browser back-stack**, which no app code
can remove. One Back past the app's entries lands on an IdP page. The protocol
layer is harmless: any re-entry mints a fresh authorization code; the redeemed
one is never reused. Whether the *pages reachable from there* are benign is
governed by **C8** (provider configuration): on a federated-only app-client with
no `COGNITO` provider, the residual is **benign**.
**Fighting the residual in-app (history trapping, popstate interception) is
prohibited**; the only full fix is a popup OAuth flow, rejected at the
architecture level.

**Bounds.** The `returnUrl` recovery guarantee is **single-concurrent-flow**
(two simultaneous sign-ins in one browser profile may overwrite each other's
recovery value). Residual behavior is verified for the Google IdP path; the
Microsoft path is config-validated, **unverified-pending** for re-traversal.

**Why.** A re-firing callback re-submits an already-redeemed authorization code
(an error), and the behavior was divergent per app — some replaced history, some
did not. Standardize the *outcome*.

**Conformance test.**
- After a successful login, the callback URL is **not** reachable via Back
  (history replaced).
- While logged out, Back from a protected page resolves to **login**.
- While logged in, a visit to the login route forwards (returnUrl-aware)
  without initiating an auth redirect and without stacking history.
- A federated-only app-client lists no `COGNITO` provider (the authoritative
  re-traversal check, cross-referencing **C8**); re-engaging an IdP page from the
  back-stack never reaches a **Cognito-native** username/password form
  (external IdPs' own credential pages are conformant).
- *(Behaviorally observable; the history-replacement mechanism is adapter-specific.)*

---

## Post-login redirect (C6)

**Rule.** There is **exactly one configured** post-login landing route. A user
bounced to login from a protected URL is returned to **that original URL**
after authenticating (`returnUrl`). The landing route is **configuration**, not
a per-app hardcoded literal.

**Why.** Fixes the divergent post-login landing route (`/admin` vs `/dashboard`
vs `/` vs `/authenticated`).

**Conformance test.**
- The landing route is read from config (the `postLoginRoute` vocabulary item
  below), not a code literal.
- A deep link to a protected URL while logged out returns the user to **that**
  URL after login.

---

## Route guards: on by default, fail-closed (C7)

**Rule.** Every protected route is guarded **by default**, and each guard is
**fail-closed**: when auth state is unknown or unresolvable, access is
**denied** (redirect to login), never granted. **No production build** exposes a
parameter, env flag, or kill-switch that disables a guard.

**Why.** Defense in depth. Forbids the whole bypass class — commented-out
guards, and query-param / env-flag / kill-switch escape hatches that disable a
guard in a production build.

**Conformance test.**
- No protected route is reachable without a guard.
- No guard has a branch that returns "allow" on the unknown/error case.
- No environment value or request parameter disables guards in a production
  build.

---

## Provider configuration & scopes (C8)

**Rule.** The set of enabled IdPs (**Google / Microsoft / both**) is selected
**per product through configuration, not by forking code**. Scopes are
standardized: baseline **`openid email profile`**; the
**`aws.cognito.signin.user.admin`** scope is **opt-in**, added only where the
app calls Cognito user APIs from the client.

**Why.** "Not all products support all providers." Fixes scope divergence and
the copy-paste-fork root cause. Changing the provider mix must not require a code
change.

**Conformance test.**
- Enabled providers derive from the `providers` config item; no provider is
  hardcoded such that changing the mix requires editing component code.
- Requested scopes equal the baseline `openid email profile` unless the admin
  scope is explicitly opted in via config.

---

## Data-layer credential is the user's token (C9)

**Rule.** Every request the app makes to a data API that authorizes per user
(GraphQL or REST) carries the signed-in user's **verified token** as a bearer
credential, and carries it **only** to the endpoints named by the `graphqlUrls`
config item. No shared secret — admin key, service token, API key — is present
in a client bundle, its environment, or its build configuration. Authorization
is derived server-side from claims on the verified token (`roleClaim`,
`defaultRoleClaim`); the client never asserts a role or identity by header.

**Why.** Three production apps shipped the data layer's admin secret in their
bundles, which handed every visitor the server's full authority and made the
login flow decorative. Sending the user's token instead lets the data layer
enforce per-user access and lets the client-side guards (C7) be what they are:
UX, not security. Scoping the header to configured endpoints keeps the token
out of third-party requests.

**Bounds.** What the data layer *grants* a verified token — role permissions,
its default role for a token that carries no role claim, its unauthorized role
for a request with no credential — is deployment configuration outside this
contract. An adapter MUST make a token that carries no role claim (the
deployment did not mint one for this app client) visible at runtime, and the
adoption guide MUST gate admin-secret removal on that check.

**Conformance test.**
- No client bundle, source tree, environment file, or build config contains a
  data-layer admin secret or a role-asserting request header.
- Every data-API request to an endpoint in `graphqlUrls` carries
  `Authorization: Bearer <verified token>`; a request to any other endpoint
  carries no token.
- A token with no role claim produces a visible runtime diagnostic naming the
  cause.

---

## Server-session profile (SP)

**Applies when** an application keeps tokens on its server and the browser never
holds them. Each item below restates one clause's outcome for that arrangement;
the wording of C1-C9 is unchanged, and an application that keeps tokens in the
browser ignores this section.

**Rule.**
- **(C2) Tokens stay server-side.** The server holds the tokens. The browser
  holds only an opaque session identifier, in a cookie marked `Secure`,
  `HttpOnly` and `SameSite=Lax` or `SameSite=Strict` (never `None`). The
  identifier is regenerated at sign-in, so one issued before sign-in never
  names the signed-in session. Verification of the token is unchanged.
- **(C3) Idle timeout is server-enforced.** Under this profile the idle timeout
  (`session.idleTimeout`) is enforced on the server, not the client. The server
  measures idleness from the session's last activity, recorded at a granularity
  of one minute or finer. Whether the browser keeps or drops its cookie has no effect on the
  timeout.
- **(C4) "Clears all locally stored tokens" means** the server's session record
  is deleted and the cookie is expired in the browser. A session identifier
  presented after logout is rejected.
- **(C5) The callback answers with a redirect.** The sign-in callback responds
  with a redirect rather than a rendered page, so it never becomes a history
  entry. Login idempotence is unchanged.
- **(C7) Requests a guard cannot redirect are refused.** A request the guard
  cannot answer with a redirect to login (not a GET, or not asking for HTML) is
  refused with 401. It is never stored as the post-login `returnUrl` and never
  replayed after sign-in.
- **(C9) Platform credentials are not data-API secrets.** The application's own
  platform credentials (for example, the keys the server uses to reach its
  session store) are not client-bundle secrets. C9 governs calls to per-user
  data APIs: no data-layer admin secret in source, environment or
  configuration.

**Why.** C2-C9 were written with a browser holding the tokens. When the server
holds them, the same outcomes are reached by different observable behavior, and
a few clauses would otherwise be unanswerable (what is "local storage" when
there is none; what is a guard's redirect for a form post).

**Conformance test.**
- No token appears in any `Set-Cookie` or response body.
- The session cookie carries `Secure`, `HttpOnly` and `SameSite=Lax` or `Strict`, and its value differs before and
  after sign-in.
- After the session has been idle for longer than `session.idleTimeout`, the
  next request demands re-authentication; an expired access token with a valid
  refresh token does not.
- After logout the old session identifier is rejected and a protected page
  demands full re-authentication.
- The callback is answered by a 3xx.
- A non-GET or non-HTML request on an expired session gets 401 and is not
  replayed after sign-in.
- No data-layer secret appears in source, environment or configuration.

---

## Config Vocabulary (machine-readable half of the port)

These items are the **stack-agnostic configuration contract**. Each adapter
provides a **typed binding** of this vocabulary (the current Angular adapter
binds it in its `auth.config` file); any other stack's adapter binds the
**same** vocabulary in its own idiom. The *names and meanings* live here (in the
port); the *encoding* lives in each adapter. Values are sourced from the Cognito
CFN `Outputs` (`infra/cognito/`).

| Item | Meaning | Drives clause |
|------|---------|---------------|
| `providers` | Enabled IdPs, e.g. `["google"]`, `["google","microsoft"]` | C8 |
| `userPoolId` | Cognito user pool id (from CFN `Outputs`) | C1–C4 |
| `clientId` | Cognito app-client id (from CFN `Outputs`) | C1 |
| `cognitoDomain` | Cognito hosted domain (authorize/logout endpoints) | C1, C4 |
| `scopes` | OAuth scopes; baseline `["openid","email","profile"]` | C8 |
| `postLoginRoute` | Single post-login landing route | C6 |
| `session.accessTtl` | Access/ID token TTL — **60 min** | C3 |
| `session.refreshTtl` | Refresh token TTL — **1 d** default (raise per product only with a recorded reason) | C3 |
| `session.idleTimeout` | Idle logout — **30 min** (client-side; no app-client field; server-side under the Server-session profile) | C3 |
| `graphqlUrls` | Data-API endpoints that receive the bearer token — absolute origins or same-origin path prefixes; empty = none | C9 |
| `roleClaim` | Claim holding the allowed roles — fleet default `hasura_allowed_roles`, read from the **ID token** | C9 |
| `defaultRoleClaim` | Claim holding the default role — fleet default `hasura_default_role`, read from the **ID token** | C9 |

> **Anti-drift rule.** Behavioral policy that code can't express lives in this
> document; everything a value can express lives in the config vocabulary. The
> two are not allowed to restate each other — a clause references the vocabulary
> item, it does not duplicate its value. (The TTLs appear above as the
> normative figures; adapter config binds to them, it does not redefine them.)

---

## What is *not* in this contract

This contract governs **authentication** and **which credential the client
sends** (C9). It does **not** enforce the following — these remain each
deployment's responsibility:

- What the data layer grants a verified token: role permissions, its default
  role for a token without a role claim, its unauthorized role for a request
  with no credential. C9 governs which credential is sent, not what it is
  granted.
- Untangling the legacy shared Cognito pool.

---

*Provenance.* This contract was derived from real divergences found across the
S4 frontend repos; this document states the contract.
