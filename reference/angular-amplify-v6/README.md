# Adapter: Angular 17 + Amplify v6

**Status:** the Angular 17 + Amplify v6 reference adapter.

This is **one adapter** of the Auth Contract (`/STANDARD.md`), not the standard
itself. It realizes every clause in `STANDARD.md` using Angular 17 standalone
components + the Amplify v6 client SDK.

**What belongs here:** framework mechanism. Amplify v6 calls, Angular guards,
`replaceUrl`, RxJS, `@ng-idle`, component templates — all the *how*.

**What does NOT belong here:** new normative rules. If you find yourself
inventing a rule, it belongs in `/STANDARD.md` (the port), not in an adapter.

**The React adapter** lives at `reference/react-oidc/` (sibling), not by editing
this one. The Contract does not move when a stack is added.

**This directory is GENERATED.** The source of truth is the ng-add templates in
`packages/angular/schematics/ng-add/files/src/app/` (that is what ships); this is
their rendering with the documented placeholder values, produced by
`packages/angular/scripts/render-reference.sh`. Edit a template, re-run the script.
`render-reference.sh --check` fails when the two drift.

## Realizes

| Clause | How this adapter realizes it |
|--------|------------------------------|
| C1 OAuth flow | `auth.config.ts` sets `loginWith.oauth.responseType:'code'`; `AuthService.signIn` calls Amplify v6 `signInWithRedirect({ provider })` — code+PKCE/S256 added by the SDK; implicit grant never selected. |
| C2 Token storage | `AuthService.getAccessToken`/`getIdToken`/`isAuthenticated`/`syncSession` read tokens ONLY from `fetchAuthSession()` (SDK/JWKS-verified: signature+`iss`+`aud`+`exp`, auto-refreshing). No `atob`; token `.payload` used for display only. Amplify default browser store (localStorage) — weakest accepted, nothing weaker. |
| C3 Session lifetime | `auth.config.ts` binds `accessTtl=60m`/`refreshTtl=1d`/`idleTimeout=30m`. `AuthService.scheduleSilentRefresh` does `fetchAuthSession({forceRefresh:true})` 5 min before expiry; `startIdleWatch`/`resetIdleTimer` (RxJS `fromEvent` activity stream, hand-rolled `@ng-idle` equivalent) fires `logout()` after 30 min idle. |
| C4 Logout | `AuthService.logout`: (1) `signOut({ global: true })` global revoke, (2) Amplify clears its token store + `clearTimers`/state reset (with `forceLocalLogout` fallback if the global call throws), (3) the SDK owns the single redirect — `auth.config.ts` sets `loginWith.oauth.redirectSignOut` to the Cognito hosted `/logout?client_id&logout_uri` URL, so `signOut` itself navigates there and ends the IdP session (no competing `window.location.assign`). No stub. |
| C5 Back-button | `CallbackComponent` (route `/auth/callback`) waits on `AuthService.signedIn$` (fired only after Amplify asynchronously consumes the `code`/`state`), then `navigateReplacingCallback` does `router.navigate(..., { replaceUrl:true })` so the consumed callback URL is dropped from history. Requires `import 'aws-amplify/auth/enable-oauth-listener'` on the redirect page. Logged-out Back from a protected page hits `authGuard` → `/login`. **C5.3 idempotence**: `LoginComponent` checks `isAuthenticated()` first and forwards to `returnUrl ?? postLoginRoute` with `replaceUrl:true` — never calls `signInWithRedirect` while authed (no `UserAlreadyAuthenticatedException`). **Residual**: external IdP pages stay in the back-stack (replaceUrl is origin-bounded); benign when the app-client passes C5.4a/C8.3. **Stall watchdog**: the callback's 15s timer can false-fail a slow-but-legit exchange (cold network) → user lands `/login?error=...`; recovery is automatic — the idempotent login forwards once the session lands. Back/Forward re-entry re-instantiates the component and re-arms the watchdog (default route reuse). |
| C6 Post-login redirect | `authGuard` attaches `returnUrl=state.url` on denial; `AuthService.signIn` passes it as `customState`, recovered via the `customOAuthState` Hub event into `pendingReturnUrl`; `resolvePostLoginTarget` reads it via `takeReturnUrl()` (NOT a query param) → returnUrl, else explicit `?returnUrl`, else the single `authConfig.postLoginRoute`. No hardcoded landing literal. |
| C7 Route guards | `authGuard` (functional `CanActivateFn`) applied by default; truth from verified session; every non-authenticated and every `catch` branch returns a redirect `UrlTree`, never `true`. `roleGuard` factory same fail-closed posture. No escape-hatch param/flag exists. |
| C8 Provider config | `auth.config.ts` `providers`/`scopes` are the sole switch; `buildAmplifyConfig` maps them into `loginWith.oauth`; `LoginComponent.providers` renders only `authConfig.providers`; `AuthService.signIn` refuses a non-configured provider. Baseline scopes `openid email profile`; admin scope opt-in. |
| C9 Data-layer credential | `auth/graphql-auth.ts`: `GraphqlAuthInterceptor` (class, registered by `provide-auth.ts` via `HTTP_INTERCEPTORS` — covers `HttpClientModule` / `withInterceptorsFromDi()` apps) and `graphqlAuthInterceptor` (functional, wired by the installer into a bare `provideHttpClient()`) attach `Authorization: Bearer <ID token>` from `fetchAuthSession()` ONLY to requests matching `authConfig.graphqlUrls` (`auth/url-allowlist.ts`, segment-boundary prefix match); `graphqlConnectionParams()` does the same for a GraphQL WebSocket. apollo-angular's `HttpLink` rides on `HttpClient`, so Apollo HTTP traffic is covered without an Apollo dependency. `auth/roles.ts` reads `hasura_allowed_roles` / `hasura_default_role` from the ID token; `roleGuard(...)` gates routes on them and denies to `/login?denied=role`; `warnIfNoRoleClaim` logs once when the token carries no role claim (the client is outside the pool's claims-emission set). |

## Layout

- `auth.config.ts` — config instance (machine-readable contract half; see `/STANDARD.md`)
- `login/` — provider-configurable login/home component
- `auth/` — auth service, guards, session/idle policy, `provide-auth.ts` (the
  app-bootstrap shim: `Amplify.configure(...)` + the C9 interceptor registration),
  `graphql-auth.ts` (C9 bearer interceptor + WebSocket `connectionParams`), and the
  two pure modules shared byte-for-byte with the React adapter — `roles.ts` and
  `url-allowlist.ts` (tested once, in the React CLI's vitest suite)

## Visual standard

`LoginComponent`'s styling — centered card, official inline provider logos, and
a plain blue-grey page background (`linear-gradient(135deg, #f0f4f8, #d9e2ec)`).
The background is the login gradient the standardized template lineage
originally shared, adopted as the single visual standard so the adapter needs no
per-repo asset wiring.

> **Note:** the earlier Cognito managed-login background was replaced with the
> repos' original gradient (2026-06-15). The capture
> `../visual-standard-dashboard-login-2026-06-11.png` predates that change and
> shows the old Cognito background — re-capture from a live login before citing
> it as the current standard.
