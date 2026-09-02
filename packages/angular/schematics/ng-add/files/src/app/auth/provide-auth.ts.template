/**
 * provide-auth.ts — Angular 17 + Amplify v6 adapter
 *
 * The app-bootstrap shim. Fills the call site that `auth.config.ts` documents
 * but does not itself provide ("Call once at app bootstrap:
 * Amplify.configure(buildAmplifyConfig(authConfig))" — auth.config.ts:189).
 * Mechanism only (the Amplify v6 configure call + Angular DI plumbing); the
 * normative outcomes live in STANDARD.md.
 *
 * Wire it into the root config — standalone `ApplicationConfig`:
 *   export const appConfig: ApplicationConfig = {
 *     providers: [provideAuth(), provideRouter(routes), ...],
 *   };
 * or, for an NgModule app, the root `AppModule`'s `providers` array
 * (`provideAuth()` returns EnvironmentProviders, valid in `@NgModule` since v14.1).
 *
 * The `s4-auth-angular` ng-add schematic derives its template from THIS file and
 * inserts `provideAuth()` into the consumer's app.config.ts OR AppModule
 * automatically (it auto-detects the bootstrap style). The React adapter
 * (reference/react-oidc/) owns its OWN bootstrap shim (AuthRoot.tsx) in its own
 * idiom — this is mechanism, not contract, so it does not move when a stack is
 * added.
 */
import { HTTP_INTERCEPTORS } from '@angular/common/http';
import { EnvironmentProviders, makeEnvironmentProviders } from '@angular/core';
import { Amplify } from 'aws-amplify';
import { cognitoUserPoolsTokenProvider } from 'aws-amplify/auth/cognito';
import { defaultStorage } from 'aws-amplify/utils';

import { authConfig, buildAmplifyConfig } from '../auth.config';
import { GraphqlAuthInterceptor } from './graphql-auth';

/**
 * Configures the Amplify v6 client from `auth.config.ts` (the single per-app
 * config surface) and returns Angular EnvironmentProviders for the root config.
 *
 * Registers the C9 bearer interceptor as a class interceptor. That reaches every
 * app whose HttpClient comes from `HttpClientModule` or from
 * `provideHttpClient(withInterceptorsFromDi())`. A standalone app that calls a bare
 * `provideHttpClient()` ignores class interceptors by design, so the installer adds
 * `withInterceptors([graphqlAuthInterceptor])` there instead — both paths run the
 * same code, and a request is only ever decorated once per interceptor.
 */
export function provideAuth(): EnvironmentProviders {
  Amplify.configure(buildAmplifyConfig(authConfig));
  // C2 — token storage = localStorage (the fleet default: persistent, multi-tab session
  // that survives reload). This is Amplify v6's default; set explicitly so the C2 choice
  // is auditable in code rather than an inherited library default. `sessionStorage` (from
  // aws-amplify/utils) is the acceptable alternative for a tab-scoped session.
  cognitoUserPoolsTokenProvider.setKeyValueStorage(defaultStorage);
  return makeEnvironmentProviders([
    { provide: HTTP_INTERCEPTORS, useClass: GraphqlAuthInterceptor, multi: true },
  ]);
}
