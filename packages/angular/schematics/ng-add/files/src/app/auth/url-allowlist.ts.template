/**
 * urlAllowlist — shared pure module (React: auth/urlAllowlist.ts; Angular: auth/url-allowlist.ts).
 * The two copies are byte-identical and the Angular schematic suite asserts it; the logic
 * is unit-tested once, in the React CLI's vitest suite. No imports, no globals.
 *
 * Realizes STANDARD.md C9 — the bearer token goes ONLY to configured data-API endpoints.
 *
 * Allowlist entries:
 *   - absolute: `https://api.example.com` or `https://api.example.com/v1` — scheme and host
 *     must match (host case-insensitive, port included), and the request path must equal
 *     the entry path or extend it at a segment boundary. A bare origin admits every path
 *     on that origin, so prefer a path where the host also serves other content.
 *   - same-origin path prefix: `/hasura-api` — for relative requests, or absolute requests
 *     to `currentOrigin` when the caller passes it (a dev-server proxy). Case-sensitive,
 *     segment-boundary match: `/hasura-api` does not match `/hasura-apiv2/x`, but does
 *     match `/hasura-api`, `/hasura-api/v1`, `/hasura-api?x`. A bare `/` is rejected: it
 *     would name every path, which is a bare-origin entry's job, said explicitly.
 *   - anything else (`api`, `https://`, `/`, an entry with a query or fragment) is malformed
 *     and matches nothing — a broken allowlist must fail closed, never wide. A
 *     protocol-relative request (`//host/x`) is cross-origin and never matches a path entry.
 */

const ABSOLUTE = /^[a-z][a-z0-9+.-]*:\/\//i;

function stripTrailingSlash(path: string): string {
  return path.length > 1 && path.endsWith('/') ? path.slice(0, -1) : path;
}

function pathOf(urlOrPath: string): string {
  const cut = urlOrPath.search(/[?#]/);
  return cut === -1 ? urlOrPath : urlOrPath.slice(0, cut);
}

function atSegmentBoundary(requestPath: string, entryPath: string): boolean {
  if (entryPath === '' || entryPath === '/') {
    return true;
  }
  return requestPath === entryPath || requestPath.startsWith(entryPath + '/');
}

function matchesAbsolute(url: string, entry: string): boolean {
  let e: URL;
  let u: URL;
  try {
    e = new URL(entry);
    u = new URL(url);
  } catch {
    return false;
  }
  if (!e.host || e.search || e.hash) {
    return false; // `https://` or an entry carrying a query/fragment is malformed
  }
  if (u.protocol !== e.protocol || u.host.toLowerCase() !== e.host.toLowerCase()) {
    return false;
  }
  return atSegmentBoundary(stripTrailingSlash(u.pathname), stripTrailingSlash(e.pathname));
}

function matchesPathPrefix(url: string, entry: string, currentOrigin?: string): boolean {
  const normalizedEntry = stripTrailingSlash(entry);
  if (normalizedEntry === '/' || /[?#]/.test(entry)) {
    return false; // `/` names every path; a query/fragment is malformed — both fail closed
  }
  if (url.startsWith('//')) {
    return false; // protocol-relative = another origin
  }
  let path = url;
  if (ABSOLUTE.test(url)) {
    // A path-only entry vouches for an absolute URL only when it is our own origin.
    if (!currentOrigin || !url.toLowerCase().startsWith(currentOrigin.toLowerCase() + '/')) {
      return false;
    }
    path = url.slice(currentOrigin.length);
  }
  return atSegmentBoundary(stripTrailingSlash(pathOf(path)), normalizedEntry);
}

/**
 * True when `url` is covered by at least one well-formed allowlist entry. Pass
 * `currentOrigin` (e.g. `window.location.origin`) so an absolute same-origin request can
 * match a path-prefix entry; without it only relative requests match path entries.
 */
export function matchesGraphqlUrl(
  url: string,
  allowlist: readonly string[],
  currentOrigin?: string,
): boolean {
  for (const raw of allowlist) {
    const entry = raw.trim();
    if (entry.length === 0) {
      continue;
    }
    if (ABSOLUTE.test(entry)) {
      if (matchesAbsolute(url, entry)) {
        return true;
      }
    } else if (entry.startsWith('/')) {
      if (matchesPathPrefix(url, entry, currentOrigin)) {
        return true;
      }
    }
    // any other shape is malformed and matches nothing
  }
  return false;
}
