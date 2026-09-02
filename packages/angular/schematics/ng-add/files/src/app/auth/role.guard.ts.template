/**
 * role.guard.ts — Angular 17 + Amplify v6 adapter
 *
 * Route-level role gate over the roles minted on the user's ID token (STANDARD.md C9
 * `roleClaim`, fleet default `hasura_allowed_roles`). Fail-closed (C7): no session,
 * no claim, or no overlap => deny.
 *
 * PLACEMENT. On the root protected route it is the app-wide floor ("only users the
 * pool minted a role for may use this app"); on a child route it is a finer gate.
 * It always denies to `/login?denied=role` — never to `postLoginRoute`, which may
 * itself sit under this guard and would loop. LoginComponent suppresses its
 * signed-in auto-forward whenever `denied` is present.
 *
 * WHAT CHANGED IN 0.4.0 (audit existing call sites): this guard used to read the
 * Cognito group-membership claim from the ACCESS token. It now reads the
 * role claim from the ID token via AuthService.getRoles(). The call shape is the
 * same, the meaning is not — `roleGuard('admin')` is a data-layer role name now.
 *
 * A pool with no role Lambda mints no claim, so this guard denies everyone there.
 * Use it only behind pools that mint roles; `warnIfNoRoleClaim` names the cause in
 * the console when it fires on a claim-less token.
 *
 * This guard gates the UI. What the token may actually read is decided by the data
 * layer from the same claims (C9) — never rely on this guard for data protection.
 */
import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';
import { fetchAuthSession } from 'aws-amplify/auth';

import { AuthService } from './auth.service';
import { hasAnyRole, warnIfNoRoleClaim } from './roles';

/**
 * Factory: guard a route on ANY of the required roles. Throws at definition time
 * on an empty requirement — an empty guard would silently lock everyone out.
 */
export function roleGuard(required: string | string[]): CanActivateFn {
  const wanted = Array.isArray(required) ? required : [required];
  if (wanted.filter((r) => r.trim().length > 0).length === 0) {
    throw new Error('roleGuard: required roles must be non-empty');
  }
  return async (): Promise<boolean | UrlTree> => {
    const router = inject(Router);
    const auth = inject(AuthService);
    try {
      const roles = await auth.getRoles();
      if (hasAnyRole(roles, wanted)) {
        return true; // C7 — the only allow path is a positive match
      }
      // Diagnose here too: a claim-less pool must be visible even before any
      // GraphQL request has fired.
      try {
        warnIfNoRoleClaim((await fetchAuthSession()).tokens?.idToken?.payload);
      } catch {
        /* diagnostic only */
      }
      return router.createUrlTree(['/login'], { queryParams: { denied: 'role' } });
    } catch {
      return router.createUrlTree(['/login'], { queryParams: { denied: 'role' } }); // C7
    }
  };
}
