# s4-auth

Standardized S4 authentication for web apps — a shared AWS Cognito stack plus
per-framework adapters that all implement one auth contract: [`STANDARD.md`](./STANDARD.md).

> **This `main` branch is the source trunk — development happens here.**
> It is *not* installed directly. Each framework's installable, self-contained
> package tree is published on its own branch (flat root, regenerated per release
> by [`scripts/export-main.sh`](./scripts/export-main.sh)).

## Install (consumers)

Pin to a release **tag** — reproducible and auditable, the right posture for an auth
boundary. (Branch tips `#angular` / `#react` track the latest build.) A published tag never
moves; the 0.3.x tags remain installable for apps not yet on the JWT data layer. Upgrading? See [`docs/MIGRATE-0.3-TO-0.4.md`](./docs/MIGRATE-0.3-TO-0.4.md) — and its
gate — first. Release notes: [`CHANGELOG.md`](./CHANGELOG.md). Cutting a release: [`RELEASING.md`](./RELEASING.md).

**Angular** (14+, standalone or NgModule):

```bash
npm i git+https://github.com/RDS-Hospitality/s4-authentication.git#angular-v0.4.0
ng g s4-auth-angular:ng-add        # prompts for Cognito values, or pass --flags
```

**React** (18+): one auto-detecting `npx` command — scaffolds a fresh Vite app for an
empty target, or injects auth into an existing one.

```bash
npx git+https://github.com/RDS-Hospitality/s4-authentication.git#react-v0.4.0 . \
  --user-pool-id <id> --client-id <id> --cognito-domain <host> --region <region>
```

The shared Cognito stack (CloudFormation template + deploy/destroy scripts) is in
[`infra/cognito/`](./infra/cognito/) — deploy it first to get the pool values the
adapters need.

## Layout (this trunk)

| Path | What |
|------|------|
| [`packages/angular/`](./packages/angular/) | Angular adapter + `ng add` schematic (source) |
| [`packages/react/`](./packages/react/) | React adapter packaging + `cli/` installer (source) |
| [`reference/react-oidc/`](./reference/react-oidc/) | React adapter **source of truth** (bundled into the CLI) |
| [`reference/angular-amplify-v6/`](./reference/angular-amplify-v6/) | Angular adapter **rendered from the ng-add templates** (`packages/angular/scripts/render-reference.sh`); the templates are the source |
| [`docs/MIGRATE-0.3-TO-0.4.md`](./docs/MIGRATE-0.3-TO-0.4.md) | Upgrade guide for installed apps — read the gate before removing an admin secret |
| [`infra/cognito/`](./infra/cognito/) | Shared Cognito CloudFormation stack |
| [`scripts/export-main.sh`](./scripts/export-main.sh) | Publishes the `angular` / `react` distribution branches + tags |

## Distribution branches

| Branch | Install ref | Built from |
|--------|-------------|------------|
| `angular` | `#angular` (latest) · `#angular-vX.Y.Z` (pinned) | `packages/angular/` + shared root |
| `react` | `#react` (latest) · `#react-vX.Y.Z` (pinned) | `packages/react/` + shared root |

Each distribution branch is a fresh single-commit orphan with everything at its root
(so `npm i` / `npx` can resolve it as a package — git installs have no "subdirectory" support).
