# Changelog

Releases are tags on the distribution branches: `angular-vX.Y.Z` and `react-vX.Y.Z`.
A tag never moves once published; older tags stay installable.

## 0.4.0 — 2026-09 (both packages)

The JWT data-layer release. Apps send the signed-in user's Cognito ID token to their
GraphQL API instead of a shared admin secret, and gate routes on the token's role claim.
New contract clause **C9** in `STANDARD.md`. Upgrade guide: `docs/MIGRATE-0.3-TO-0.4.md`
— read its gate before removing any admin secret.

### s4-auth-angular 0.4.0 (was 0.3.1)

Added
- `auth/graphql-auth.ts`: `GraphqlAuthInterceptor` (class, registered by `provideAuth()`) and
  `graphqlAuthInterceptor` (functional, wired by `ng add` into a bare `provideHttpClient()`)
  attach `Authorization: Bearer <ID token>` only to requests matching `authConfig.graphqlUrls`;
  `graphqlConnectionParams()` for GraphQL WebSockets.
- `auth/roles.ts` and `auth/url-allowlist.ts` — pure modules shared byte-for-byte with the
  React adapter; `AuthService.getRoles()`; `state.role`.
- `auth.config.ts` `graphqlUrls`; `ng add` option `--post-login-route` (default `/`, must start
  with `/`); `ng add` now patches `provideHttpClient(...)` with the interceptor feature or warns.
- Login page shows a denial notice for any `?denied=` value and never auto-forwards then.

Changed — **breaking**
- `roleGuard(required)` reads `hasura_allowed_roles` from the **ID token** (was the Cognito group
  claim from the access token). Same call shape, different meaning: audit every call site. It
  denies to `/login?denied=role` (was bare `/login`) and throws on an empty requirement.
- `auth.config.ts` `allowedEmailDomains` and the email-domain branch in `authGuard` are removed.
  Sign-in eligibility is enforced at the pool (inbound-federation gate); route-level role gating
  is `roleGuard`. `authGuard` answers only "is there a verified session".
- `postLoginRoute` default `/` (was `/home`).

### @s4/auth-react 0.4.0 (was 0.3.2)

Added
- `auth/graphqlAuth.ts`: `graphqlAuthHeaders()`, `authFetch()`, `graphqlConnectionParams()` —
  non-hook helpers that share the provider's `UserManager`, renew an expired token once and never
  send a stale one.
- `auth/roles.ts` and `auth/urlAllowlist.ts` (shared with Angular); `useAuthService().roles` /
  `.role`; `auth.config.ts` `graphqlUrls`, `buildUserManagerSettings()`, `getUserManager()`,
  `buildProviderProps()`.
- `LoginLocationState.denied`; `LoginPage` shows the denial and does not auto-forward.
- `LoginPage` renders the sign-in error `CallbackPage` forwards (0.3.2 dropped it).

Changed — **breaking**
- `<RequireRole anyOf>` reads `hasura_allowed_roles` from the ID token (was the Cognito group
  claim) and denies to `/login` with `denied: 'role'` (was `postLoginRoute`); throws on empty.
- `AuthRoot` passes a shared `UserManager` (`buildProviderProps()`); `buildOidcConfig()` is a
  deprecated alias, removed in 0.5.0.
- CLI `--post-login-route` default `/` (was `/home`).

### Release process
- `scripts/export-main.sh` mints annotated tags, refuses to republish different content under an
  existing version, leaves the tag untouched on an identical re-run, validates semver, and
  serialises concurrent runs. `test-export-main.sh` asserts all of it.
- GitHub tag ruleset (deny deletion / update) on `refs/tags/**`.

## 0.3.x — 2026-07

- `angular-v0.3.1` (48a3f1c), `react-v0.3.2` (1138f83): the code-flow adapters as first
  published on this repository. Still installable; pre-C9 (no GraphQL helpers, email-domain gate
  in the Angular guard, group-claim role guards).
