/**
 * loginState.ts — React + react-oidc-context adapter
 *
 * The router-state contract between the pages that SEND a user to /login and the
 * LoginPage that receives them:
 *   - RequireAuth forwards `returnUrl` (C6) when it bounces an unauthenticated visit.
 *   - CallbackPage forwards `error` when the OIDC code exchange fails (C7 spirit).
 *   - RequireRole forwards `denied: 'role'` for a signed-in user without the role; the
 *     LoginPage must then NOT auto-forward them back into the app (it would loop).
 *
 * React Router types `location.state` as `unknown`, so a writer and a reader that each
 * spell the shape inline can drift apart with no compile error — that is exactly how the
 * first React port shipped a forwarded `error` that no LoginPage ever displayed. Both sides
 * import this one type, and readers go through `readLoginState` so a malformed or foreign
 * state degrades to "no returnUrl, no error" rather than throwing.
 *
 * Deliberately imports nothing from 'react-router': the installer rewrites router imports
 * from a fixed file list, and a pure module stays off that list.
 */

export interface LoginLocationState {
  /** In-app path to land on after sign-in (C6). Same-tab fallback for the OAuth `state`. */
  returnUrl?: string;
  /** Human-readable reason the previous sign-in attempt failed. Rendered by LoginPage. */
  error?: string;
  /** Set when a signed-in user was turned away by a role gate. Suppresses auto-forward. */
  denied?: 'role';
}

export function readLoginState(state: unknown): LoginLocationState {
  if (!state || typeof state !== 'object') {
    return {};
  }
  const candidate = state as Record<string, unknown>;
  const out: LoginLocationState = {};
  if (typeof candidate.returnUrl === 'string' && candidate.returnUrl.length > 0) {
    out.returnUrl = candidate.returnUrl;
  }
  if (typeof candidate.error === 'string' && candidate.error.length > 0) {
    out.error = candidate.error;
  }
  if (candidate.denied === 'role') {
    out.denied = 'role';
  }
  return out;
}
