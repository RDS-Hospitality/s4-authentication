/**
 * RequireRole.tsx — React + react-oidc-context adapter
 *
 * Route-level role gate over the roles minted on the user's ID token (STANDARD.md C9
 * `roleClaim`, fleet default `hasura_allowed_roles`). Composes ON TOP of RequireAuth
 * (authentication first, authorization second). Reads the VERIFIED id_token claims the
 * library exposes (auth.user.profile), never a hand-decoded token (C2). Fail-closed (C7).
 * Analog of angular-amplify-v6/auth/role.guard.ts.
 *
 * PLACEMENT. Wrapping the root protected layout makes it the app-wide floor ("only users
 * the pool minted a role for may use this app"); wrapping a child route makes it a finer
 * gate. A signed-in user without the role is sent to /login with `denied: 'role'` — never
 * to postLoginRoute, which may itself sit under this wrapper and would loop. LoginPage
 * suppresses its auto-forward when `denied` is present.
 *
 * WHAT CHANGED IN 0.4.0 (audit existing call sites): this used to read the Cognito
 * group-membership claim. `anyOf` names data-layer roles now.
 *
 * A pool with no role Lambda mints no claim, so this denies everyone there; use it only
 * behind pools that mint roles. warnIfNoRoleClaim names the cause in the console.
 *
 *   <RequireAuth><RequireRole anyOf={['dashboard_readonly']}><AppLayout/></RequireRole></RequireAuth>
 */
import React from 'react';
import { Navigate } from 'react-router';
import { useAuth } from 'react-oidc-context';

import type { LoginLocationState } from '../login/loginState';
import { hasAnyRole, readRoles, warnIfNoRoleClaim } from './roles';

export function RequireRole({
  anyOf,
  children,
}: {
  anyOf: string | string[];
  children: React.ReactNode;
}) {
  const auth = useAuth();
  // Throws on an empty requirement — an empty gate would silently lock everyone out.
  const wanted = Array.isArray(anyOf) ? anyOf : [anyOf];
  if (wanted.filter((r) => r.trim().length > 0).length === 0) {
    throw new Error('RequireRole: anyOf must be non-empty');
  }

  // C7 — still resolving is not "allow".
  if (auth.isLoading) {
    return null;
  }
  // C7 — unauthenticated denies to login (RequireAuth normally catches this first).
  if (!auth.isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  const roles = readRoles(auth.user?.profile);
  if (hasAnyRole(roles, wanted)) {
    return <>{children}</>;
  }
  // Diagnose a claim-less pool here too, before any GraphQL request has fired.
  warnIfNoRoleClaim(auth.user?.profile);
  const state: LoginLocationState = { denied: 'role' };
  return <Navigate to="/login" replace state={state} />;
}
