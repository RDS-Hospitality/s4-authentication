/**
 * graphql-auth.ts — Angular 17 + Amplify v6 adapter
 *
 * Realizes STANDARD.md C9 — every request to a configured data-API endpoint
 * (`authConfig.graphqlUrls`) carries the signed-in user's verified token as a bearer
 * credential, and nothing else does. Mechanism only; the normative outcome is C9.
 *
 * Three entry points, one behaviour:
 *   - `graphqlAuthInterceptor` (functional) — for `provideHttpClient(withInterceptors([...]))`.
 *   - `GraphqlAuthInterceptor` (class) — registered by provide-auth.ts for
 *     `HttpClientModule` / `withInterceptorsFromDi()` apps.
 *   - `graphqlConnectionParams()` — for a GraphQL WebSocket client's `connectionParams`,
 *     which HttpClient never sees. Resolved once per connection; a reconnect re-runs it.
 * apollo-angular's HttpLink is built on HttpClient, so the interceptors cover Apollo HTTP
 * traffic without this adapter depending on Apollo.
 *
 * The token is the ID token (GRAPHQL_TOKEN). The fleet's role Lambda mints its claims on
 * both tokens, so switching is this one constant. `fetchAuthSession` is SDK-verified and
 * refreshes near expiry (C2/C3); no token is ever decoded here to make a decision.
 */
import {
  HttpEvent,
  HttpHandler,
  HttpHandlerFn,
  HttpInterceptor,
  HttpInterceptorFn,
  HttpRequest,
} from '@angular/common/http';
import { Injectable } from '@angular/core';
import { fetchAuthSession } from 'aws-amplify/auth';
import { from, Observable, switchMap } from 'rxjs';

import { authConfig } from '../auth.config';
import { warnIfNoRoleClaim } from './roles';
import { matchesGraphqlUrl } from './url-allowlist';

/** Which token is the data-layer credential. The role claims are minted on both. */
export const GRAPHQL_TOKEN: 'id' | 'access' = 'id';

/**
 * `{ Authorization: 'Bearer <token>' }` from the verified session, or `{}` when there is
 * no session (the data layer then treats the request as unauthenticated — C7: never
 * invent a credential). Also raises the C9 diagnostic when the token carries no role
 * claim, so a client left out of the claims-emission set is visible at first use.
 */
export async function graphqlAuthHeaders(): Promise<Record<string, string>> {
  try {
    const session = await fetchAuthSession();
    const jwt = GRAPHQL_TOKEN === 'id' ? session.tokens?.idToken : session.tokens?.accessToken;
    if (!jwt) {
      return {};
    }
    warnIfNoRoleClaim(session.tokens?.idToken?.payload);
    return { Authorization: `Bearer ${jwt.toString()}` };
  } catch {
    return {}; // C7 — an error path yields no credential, never a stale one
  }
}

/** `connectionParams` for graphql-ws / subscriptions-transport-ws clients. */
export async function graphqlConnectionParams(): Promise<{ headers: Record<string, string> }> {
  return { headers: await graphqlAuthHeaders() };
}

function attachIfAllowed(
  req: HttpRequest<unknown>,
  next: (req: HttpRequest<unknown>) => Observable<HttpEvent<unknown>>,
): Observable<HttpEvent<unknown>> {
  const origin = typeof window !== 'undefined' ? window.location.origin : undefined;
  if (!matchesGraphqlUrl(req.url, authConfig.graphqlUrls, origin)) {
    return next(req);
  }
  return from(graphqlAuthHeaders()).pipe(
    switchMap((headers) => next(headers['Authorization'] ? req.clone({ setHeaders: headers }) : req)),
  );
}

/** Functional form — `provideHttpClient(withInterceptors([graphqlAuthInterceptor]))`. */
export const graphqlAuthInterceptor: HttpInterceptorFn = (req, next: HttpHandlerFn) =>
  attachIfAllowed(req, next);

/** Class form — registered via HTTP_INTERCEPTORS in provide-auth.ts. */
@Injectable()
export class GraphqlAuthInterceptor implements HttpInterceptor {
  intercept(req: HttpRequest<unknown>, next: HttpHandler): Observable<HttpEvent<unknown>> {
    return attachIfAllowed(req, (r) => next.handle(r));
  }
}
