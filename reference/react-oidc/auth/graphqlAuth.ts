/**
 * graphqlAuth.ts — React + react-oidc-context adapter
 *
 * Realizes STANDARD.md C9 — every request to a configured data-API endpoint
 * (`authConfig.graphqlUrls`) carries the signed-in user's verified token as a bearer
 * credential, and nothing else does. Mechanism only. Analog of
 * angular-amplify-v6/auth/graphql-auth.ts.
 *
 * These helpers run OUTSIDE React components (an Apollo link, a graphql-ws client, a plain
 * fetch in a store), so they cannot use the useAuth() hook. They read the same UserManager
 * the <AuthProvider> drives (auth.config getUserManager), so the session, its silent
 * renewals and its store are shared — nothing here re-derives the storage key or parses
 * storage by hand.
 *
 *   Apollo:      setContext(async () => ({ headers: await graphqlAuthHeaders() }))
 *   graphql-ws:  createClient({ url, connectionParams: graphqlConnectionParams })
 *   fetch:       authFetch(url, init)
 *
 * The token is the ID token (GRAPHQL_TOKEN). The fleet's role Lambda mints its claims on
 * both tokens, so switching is this one constant. No token is decoded here to make a
 * decision; the data layer verifies it (C2).
 *
 * STATUS: no React consumer runs this against a live pool yet — verified by typecheck and
 * unit tests only. The Angular sibling is proven in production (culvers, 2026-08-28).
 */
import type { User, UserManager } from 'oidc-client-ts';

import { authConfig, getUserManager } from '../auth.config';
import { warnIfNoRoleClaim } from './roles';
import { matchesGraphqlUrl } from './urlAllowlist';

/** Which token is the data-layer credential. The role claims are minted on both. */
export const GRAPHQL_TOKEN: 'id' | 'access' = 'id';

/** One in-flight silent renewal per manager: N concurrent expired callers share it. */
const renewals = new WeakMap<UserManager, Promise<User | null>>();

function renewOnce(um: UserManager): Promise<User | null> {
  let pending = renewals.get(um);
  if (!pending) {
    pending = um
      .signinSilent()
      .catch(() => null) // blocked third-party cookies, revoked refresh token, offline
      .finally(() => renewals.delete(um));
    renewals.set(um, pending);
  }
  return pending;
}

/**
 * The current user with a non-expired token, renewing once if needed, or null. The
 * library does not filter `getUser()` on expiry, so the check is ours (C3/C7): an
 * expired token is never sent — better no credential than a stale one.
 */
export async function getGraphqlUser(um: UserManager = getUserManager()): Promise<User | null> {
  let user = await um.getUser();
  if (!user || user.expired) {
    user = await renewOnce(um);
  }
  return user && !user.expired ? user : null;
}

/**
 * `{ Authorization: 'Bearer <token>' }` from the shared session, or `{}` when there is no
 * usable session (the data layer then treats the request as unauthenticated — C7: never
 * invent a credential). Raises the C9 diagnostic when the token carries no role claim, so
 * a client left out of the claims-emission set is visible at first use.
 */
export function graphqlAuthHeaders(): Promise<Record<string, string>> {
  return graphqlAuthHeadersFrom(getUserManager());
}

/** Same, against an explicit manager — the seam the unit tests use. */
export async function graphqlAuthHeadersFrom(um: UserManager): Promise<Record<string, string>> {
  try {
    const user = await getGraphqlUser(um);
    if (!user) {
      return {};
    }
    const token = GRAPHQL_TOKEN === 'id' ? user.id_token : user.access_token;
    if (!token) {
      return {};
    }
    warnIfNoRoleClaim(user.profile);
    return { Authorization: `Bearer ${token}` };
  } catch {
    return {};
  }
}

/** `connectionParams` for graphql-ws / subscriptions-transport-ws clients. */
export async function graphqlConnectionParams(): Promise<{ headers: Record<string, string> }> {
  return { headers: await graphqlAuthHeaders() };
}

/**
 * `fetch` that attaches the bearer header ONLY when the URL is in `authConfig.graphqlUrls`
 * (C9 — the token never reaches a third-party host). Everything else is passed through.
 */
export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  // A Request or URL is already absolute; pass our origin so a same-origin one can still
  // match a path-prefix entry such as a dev-server proxy.
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  const origin = typeof window !== 'undefined' ? window.location.origin : undefined;
  if (!matchesGraphqlUrl(url, authConfig.graphqlUrls, origin)) {
    return fetch(input, init);
  }
  const auth = await graphqlAuthHeaders();
  const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
  if (auth['Authorization']) {
    headers.set('Authorization', auth['Authorization']);
  }
  return fetch(input, { ...init, headers });
}
