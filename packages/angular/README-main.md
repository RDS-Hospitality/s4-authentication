# s4-auth-angular

Standardized S4 authentication for **Angular 14+** apps — **standalone or NgModule** (auto-detected) — Cognito + Amplify v6,
installed via the Angular CLI. This `angular` branch is a **built, installable package** with
everything at its root; it is regenerated per release and is not where development happens
(development lives on `main`).

> The auth contract this implements is [`STANDARD.md`](./STANDARD.md).

## Install (git-URL, two steps)

```bash
# 1. add the Angular package — pinned to a release tag (reproducible; recommended for auth)
npm i git+https://github.com/RDS-Hospitality/s4-authentication.git#angular-v0.4.0

#    …or track the branch tip for the latest build:
#    npm i git+https://github.com/RDS-Hospitality/s4-authentication.git#angular

# 2. run the installer schematic (prompts for pool values, or pass flags)
ng g s4-auth-angular:ng-add \
  --user-pool-id=us-east-1_xxxx \
  --client-id=xxxxxxxxxxxxxxxxxxxxxx \
  --cognito-domain=your-prefix.auth.us-east-1.amazoncognito.com \
  --providers=google \
  --post-login-route=/
```

This scaffolds the auth source into `src/app/` (you own and may edit it), inserts
`provideAuth()` into the root config (`app.config.ts` for standalone apps, `AppModule`
for NgModule apps — auto-detected), adds the `login` + `auth/callback` routes (into
`app.routes.ts` or `app-routing.module.ts`), wires the C9 bearer interceptor into a
standalone app's `provideHttpClient(...)` (or tells you to), and adds `aws-amplify@^6.17.0`.

## Send the user's token to your GraphQL API (C9)

**Gate first:** your app's Cognito client must be in the pool's claims-emission set before you
remove an admin secret — see [`docs/MIGRATE-0.3-TO-0.4.md`](https://github.com/RDS-Hospitality/s4-authentication/blob/main/docs/MIGRATE-0.3-TO-0.4.md) step 0.

1. Set `graphqlUrls` in `src/app/auth.config.ts`, e.g. `['https://api.s4hospitality.net', '/hasura-api']`.
2. Attach the header:
   - `HttpClientModule` or `provideHttpClient(withInterceptorsFromDi())` apps: nothing to do —
     `provideAuth()` registers the class interceptor, and apollo-angular's `HttpLink` uses `HttpClient`.
   - Standalone `provideHttpClient()`: `ng add` inserts `withInterceptors([graphqlAuthInterceptor])`;
     if you add HttpClient later, add it yourself (`import { graphqlAuthInterceptor } from './auth/graphql-auth'`).
   - GraphQL WebSocket: `connectionParams: graphqlConnectionParams` (same module).
3. Roles: `roleGuard('dashboard_readonly')` on the root protected route is the app-wide floor
   (it reads `hasura_allowed_roles` from the ID token and denies to `/login?denied=role`);
   `AuthService.getRoles()` / `state().role` for display. Do not use it behind a pool that mints
   no role claim — it denies everyone there.

If the console shows `s4-auth: … token carries no "hasura_allowed_roles" claim`, the client is not
in the emission set: the data layer is applying its own default role. Stop and fix step 0.

> Prefer to wire it in by hand? See [`schematics/MANUAL-INSTALL.md`](./schematics/MANUAL-INSTALL.md).

## Need a Cognito pool first? (greenfield)

The pool/template lives in [`infra/cognito/`](./infra/cognito/). Deploy it, then bridge its
outputs into your config one of two ways:

- **Paste-block (default):** after deploy, read the stack's `AuthConfigBlock` output and paste
  the three values into `src/app/auth.config.ts`.
- **Fetch-helper (opt-in):** `infra/cognito/scripts/fetch-config.sh` (or `.ps1`) runs read-only
  `describe-stacks` and writes them for you.

Deploy/destroy scripts (PowerShell + shell) are in `infra/cognito/scripts/`.
