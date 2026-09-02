# How to migrate an installed app from 0.3.x to 0.4.0

For an app that already ran `ng add s4-auth-angular` (0.3.1) or the `@s4/auth-react` installer
(0.3.2) and now wants to send the user's token to its GraphQL API instead of an admin secret.
The two worked examples are the `culvers-jwt` and `slims-staging-jwt` branches of
`dashboard-project`; this guide is their diff, generalised.

## 0. Gate — do this before touching code

The adapter sends the token. **What the data layer does with it is decided elsewhere**, and the
deciding piece is fail-open: the pool's PreTokenGeneration Lambda mints the `hasura_*` role
claims **only for app clients in its emission set**. A client outside it gets a token with no
role claim; Hasura then applies its `claims_map` default role (on rds-cloud: `unassigned`), so
the app runs as a role nobody sized for it. The domain gate is the opposite (fail-closed per
client), so "the domain gate let me in" proves nothing about roles.

Confirm both, and write the answers in the app's PR:

- [ ] **(a) Sign-in gate.** The app client is in the inbound-federation domain-gate allowlist
      for the pool (user-pool-project `infra/lambda/domain-gate/`).
- [ ] **(b) Claims emission.** The app client is in the claims Lambda's emission set. Today that is
      the `POC_CLIENT_ID` variable on `google-prod-hasura-role-claims`:
      ```bash
      aws lambda get-function-configuration --function-name google-prod-hasura-role-claims \
        --region us-east-1 --query 'Environment.Variables.POC_CLIENT_ID' --output text
      ```
      If it is not your client, **stop here**: keep the admin-secret path and get the client added
      (user-pool-project, `wl-hasura-poc-loose-ends`) — or confirm with the Hasura owner that the
      instance's default role for a claim-less token is acceptable for this app (it is for the
      Slims silo, whose `claims_map` default is `dashboard_readonly`).
- [ ] **(c)** Your Hasura instance trusts the pool (its `HASURA_GRAPHQL_JWT_SECRETS` has an entry
      with the pool's `jwk_url`/`issuer`) and has a role sized for this app.

Recommended: deploy the migrated branch **side by side** (separate Amplify branch + subdomain,
its callback/logout URLs added to the Cognito client) before flipping the live branch, as
culvers-jwt was.

## 1. Update the adapter files

Angular — re-run the installer or copy the changed files from the `angular-v0.4.0` tree
(`schematics/ng-add/files/src/app/`, drop `.template`):
`auth.config.ts`, `auth/provide-auth.ts`, `auth/auth.service.ts`, `auth/auth.guard.ts`,
`auth/role.guard.ts`, `login/login.component.ts`, plus the new `auth/graphql-auth.ts`,
`auth/roles.ts`, `auth/url-allowlist.ts`. Re-apply your pool values and `providers`/`appTitle`.

React — re-run `npx …#react-v0.4.0 . --force` or copy the changed files from `templates/`:
`auth.config.ts`, `auth/AuthRoot.tsx`, `auth/useAuthService.ts`, `auth/RequireRole.tsx`,
`login/LoginPage.tsx`, `login/loginState.ts`, plus the new `auth/graphqlAuth.ts`,
`auth/roles.ts`, `auth/urlAllowlist.ts`.

## 2. Configure the data-API endpoints

Set `graphqlUrls` in `auth.config.ts`: absolute origins and/or a same-origin dev-proxy prefix,
e.g. `['https://api.s4hospitality.net', '/hasura-api']`. Path-scope the entry when the host also
serves other content; a bare origin sends the token on every request to it.

## 3. Attach the token

- **Angular, `HttpClientModule` or `provideHttpClient(withInterceptorsFromDi())`:** nothing —
  `provideAuth()` registers the class interceptor. apollo-angular's `HttpLink` uses `HttpClient`,
  so Apollo HTTP traffic is covered.
- **Angular, standalone `provideHttpClient()`:** add `withInterceptors([graphqlAuthInterceptor])`
  (`ng add` does this for you when it finds the call).
- **Angular, GraphQL WebSocket:** `connectionParams: graphqlConnectionParams`.
- **React:** `setContext(async () => ({ headers: await graphqlAuthHeaders() }))` for Apollo,
  `connectionParams: graphqlConnectionParams` for graphql-ws, or `authFetch` for plain fetch.

## 4. Remove the admin secret and the app-side Hasura guards

Delete `X-Hasura-Admin-Secret` / `authorizationToken` / `useUserTokens` from `environment.ts`,
`graphql.module.ts`, `amplify.yml` secret injection, and docs. Drop any app guard that looks the
user up in Hasura to decide access (slims-staging-jwt deleted its `AuthGuard`/`RoleGuard`); the
adapter's `authGuard` + `roleGuard` are the gates.

## 5. Audit role-guard call sites — the meaning changed

`roleGuard('x')` / `<RequireRole anyOf={['x']}>` now test `hasura_allowed_roles` on the ID token,
not a Cognito group. Every existing call compiles unchanged and means something different. For an
app-wide floor put the guard on the root protected route. Do not use it on a pool that mints no
claims (Slims): it denies everyone there.

## 6. Post-login route

`ng add` now asks for `postLoginRoute` (default `/`). If your copy says `/home` and no such
route exists, change it — culvers landed on `/notfound` after every logout for this reason.

## 7. Repoint and re-resolve the pin

```json
"s4-auth-angular": "github:RDS-Hospitality/s4-authentication#angular-v0.4.0"
```
then `npm install` and commit `package-lock.json` — `npm ci` keeps the old resolved SHA
otherwise. (Pins that still say `ntanner-ctrl/…` redirect, but fix them.)

## 8. Verify from the deployed app

- Network tab: every request to a `graphqlUrls` host carries `Authorization: Bearer …`; a request
  to any other host carries none; **no** `x-hasura-admin-secret` anywhere.
- Console: no `s4-auth: … no "hasura_allowed_roles" claim` error. If you see it, step 0(b) failed.
- **Confirm the role, not just success.** On an instance whose unauthorized role is `site`, an
  HTTP 200 proves nothing. Issue one query your role must NOT be able to run and confirm Hasura
  denies it, naming your role in the error.
- Sign out; confirm `/login`, and that a protected route no longer renders.
