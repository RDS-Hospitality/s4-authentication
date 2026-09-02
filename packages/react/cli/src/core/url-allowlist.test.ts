// Spec-blind tests (blueprint jwt-release-0.4, tests.md §a) for the shared pure matcher.
// The Angular template copy is byte-identical (jasmine drift spec), so this suite tests both.
import { describe, it, expect } from "vitest";
import { matchesGraphqlUrl } from "../../../../../reference/react-oidc/auth/urlAllowlist";

describe("matchesGraphqlUrl", () => {
  // --- spec-given cases ---
  it("rejects a different origin entirely", () => {
    expect(matchesGraphqlUrl("https://evil.example/x", ["https://api.s4hospitality.net"])).toBe(false);
  });
  it("matches a path-prefixed allowlist entry", () => {
    expect(matchesGraphqlUrl("/hasura-api/v1/graphql", ["/hasura-api"])).toBe(true);
  });
  it("rejects a path that only shares a string prefix, not a path-segment boundary", () => {
    expect(matchesGraphqlUrl("/hasura-apiv2/v1/graphql", ["/hasura-api"])).toBe(false);
  });
  it("matches when the request path carries a query string", () => {
    expect(matchesGraphqlUrl("/hasura-api?x=1", ["/hasura-api"])).toBe(true);
  });
  it("rejects a host that merely starts with the allowed origin (subdomain-suffix attack)", () => {
    expect(matchesGraphqlUrl("https://api.s4hospitality.net.evil.com/", ["https://api.s4hospitality.net"])).toBe(false);
  });
  it("matches case-insensitively on host", () => {
    expect(matchesGraphqlUrl("https://API.s4hospitality.net/v1/graphql", ["https://api.s4hospitality.net"])).toBe(true);
  });
  it('rejects the bare scheme "https://" as an allowlist entry', () => {
    expect(matchesGraphqlUrl("https://api.s4hospitality.net/v1/graphql", ["https://"])).toBe(false);
  });
  it('rejects the bare word "api" as an allowlist entry', () => {
    expect(matchesGraphqlUrl("https://api.s4hospitality.net/v1/graphql", ["api"])).toBe(false);
  });
  // --- derived boundary cases ---
  it("matches when the allowlist entry itself carries a trailing slash", () => {
    expect(matchesGraphqlUrl("/hasura-api/v1/graphql", ["/hasura-api/"])).toBe(true);
  });
  it("does not case-fold a path-only entry (no host to normalize)", () => {
    expect(matchesGraphqlUrl("/Hasura-Api/v1/graphql", ["/hasura-api"])).toBe(false);
  });
  it("rejects when the allowlist entry itself carries a query string (malformed config)", () => {
    expect(matchesGraphqlUrl("/hasura-api/v1/graphql", ["/hasura-api?x=1"])).toBe(false);
  });
  it("rejects on scheme mismatch even when host and path match", () => {
    expect(matchesGraphqlUrl("http://api.s4hospitality.net/v1/graphql", ["https://api.s4hospitality.net"])).toBe(false);
  });
  it("returns false for every url when the allowlist is empty", () => {
    expect(matchesGraphqlUrl("https://api.s4hospitality.net/v1/graphql", [])).toBe(false);
    expect(matchesGraphqlUrl("/hasura-api/v1/graphql", [])).toBe(false);
  });
  // --- review findings: a bare "/" entry and protocol-relative URLs must fail closed ---
  it('rejects a bare "/" entry — it would name every path', () => {
    expect(matchesGraphqlUrl("/graphql", ["/"])).toBe(false);
    expect(matchesGraphqlUrl("//evil.example/graphql", ["/"])).toBe(false);
  });
  it("never matches a protocol-relative URL against a path entry", () => {
    expect(matchesGraphqlUrl("//evil.example/hasura-api/x", ["/hasura-api"])).toBe(false);
  });
  // --- same-origin absolute requests (Request/URL inputs) match a path entry only with currentOrigin ---
  it("matches an absolute same-origin URL against a path entry when the origin is given", () => {
    expect(matchesGraphqlUrl("https://app.example.com/hasura-api/v1/graphql", ["/hasura-api"], "https://app.example.com")).toBe(true);
    expect(matchesGraphqlUrl("https://APP.example.com/hasura-api/v1/graphql", ["/hasura-api"], "https://app.example.com")).toBe(true);
  });
  it("does not let a path entry match another origin even when an origin is given", () => {
    expect(matchesGraphqlUrl("https://evil.example.com/hasura-api/v1/graphql", ["/hasura-api"], "https://app.example.com")).toBe(false);
    expect(matchesGraphqlUrl("https://app.example.com.evil/hasura-api/x", ["/hasura-api"], "https://app.example.com")).toBe(false);
  });
  it("without an origin, an absolute URL never matches a path entry", () => {
    expect(matchesGraphqlUrl("https://app.example.com/hasura-api/v1/graphql", ["/hasura-api"])).toBe(false);
  });

  // --- absolute entry with a path, exact-origin request (the dashboards' shape) ---
  it("matches an absolute origin entry against a request to a path under it", () => {
    expect(matchesGraphqlUrl("https://api.s4hospitality.net/v1/graphql", ["https://api.s4hospitality.net"])).toBe(true);
  });
  it("matches an absolute entry that carries a path only at a segment boundary", () => {
    expect(matchesGraphqlUrl("https://api.s4hospitality.net/v1/graphql", ["https://api.s4hospitality.net/v1"])).toBe(true);
    expect(matchesGraphqlUrl("https://api.s4hospitality.net/v10/graphql", ["https://api.s4hospitality.net/v1"])).toBe(false);
  });
});
