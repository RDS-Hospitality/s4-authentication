/**
 * roles — shared pure module (React: auth/roles.ts; Angular: auth/roles.ts).
 * The two copies are byte-identical and the Angular schematic suite asserts it; the logic
 * is unit-tested once, in the React CLI's vitest suite. No imports, no globals.
 *
 * Realizes STANDARD.md C9 vocabulary: `roleClaim` / `defaultRoleClaim`, read from the ID
 * token. The fleet's PreTokenGeneration Lambda mints both claims on both tokens.
 *
 * A token WITHOUT the claim is not an error here — the pool did not mint one for this app
 * client (it is outside the claims-emission set), or the pool has no role Lambda. The data
 * layer then applies its own default role, so the condition must be loud: every consumer
 * routes through `warnIfNoRoleClaim`, which names the cause once per log sink.
 */

/** Vocab `roleClaim` — the allowed-roles claim. */
export const ROLE_CLAIM = 'hasura_allowed_roles';
/** Vocab `defaultRoleClaim` — the default-role claim. */
export const DEFAULT_ROLE_CLAIM = 'hasura_default_role';
/** Which token the claims are read from. */
export const ROLE_CLAIM_TOKEN: 'id' | 'access' = 'id';

type Claims = Record<string, unknown>;

function claims(payload: unknown): Claims | undefined {
  return payload && typeof payload === 'object' ? (payload as Claims) : undefined;
}

function cleanList(value: unknown): string[] {
  const list = Array.isArray(value) ? value : typeof value === 'string' ? [value] : [];
  return list
    .filter((v): v is string => typeof v === 'string')
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
}

/**
 * The roles minted on the token, normalised: a bare string becomes a one-element list,
 * entries are trimmed, blanks and non-strings dropped, order and duplicates preserved.
 * `[]` for no payload, no claim, or a malformed claim.
 */
export function readRoles(payload: unknown): string[] {
  return cleanList(claims(payload)?.[ROLE_CLAIM]);
}

/** The default role minted on the token, trimmed, or undefined. Display only. */
export function readDefaultRole(payload: unknown): string | undefined {
  const value = claims(payload)?.[DEFAULT_ROLE_CLAIM];
  const role = typeof value === 'string' ? value.trim() : '';
  return role.length > 0 ? role : undefined;
}

/**
 * True when `roles` contains ANY of `required`. Case-sensitive: data-layer role names are.
 * Throws on an empty requirement — an empty gate would silently lock everyone out and
 * be indistinguishable from a correctly denied user.
 */
export function hasAnyRole(roles: readonly string[], required: string | readonly string[]): boolean {
  const wanted = cleanList(required);
  if (wanted.length === 0) {
    throw new Error('roleGuard/RequireRole: required roles must be non-empty');
  }
  return wanted.some((r) => roles.includes(r));
}

const warnedSinks = new WeakSet<object>();

/**
 * Logs once per log sink when the token carries no allowed-roles claim, and returns
 * whether it warned (true also on the suppressed repeats). Keyed on the sink rather than
 * a bare module flag so tests and multiple sinks each see the warning once; in an app the
 * sink is `console.error`, so it fires once per page load.
 */
export function warnIfNoRoleClaim(
  payload: unknown,
  log: (message: string) => void = console.error,
): boolean {
  if (readRoles(payload).length > 0) {
    return false;
  }
  if (!warnedSinks.has(log)) {
    warnedSinks.add(log);
    log(
      `s4-auth: the signed-in user's token carries no "${ROLE_CLAIM}" claim — this app client is not in ` +
        `the pool's claims-emission set (or the pool has no role Lambda). The data layer will apply its ` +
        `own default role. Do not remove an admin secret until the emission set includes this client.`,
    );
  }
  return true;
}
