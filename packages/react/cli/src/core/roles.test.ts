// Spec-blind tests (blueprint jwt-release-0.4, tests.md §b) for the shared pure role helpers.
import { describe, it, expect, vi } from "vitest";
import { hasAnyRole, readRoles, readDefaultRole, warnIfNoRoleClaim } from "../../../../../reference/react-oidc/auth/roles";

describe("warnIfNoRoleClaim", () => {
  it("logs once and returns true when the claims object has no role fields at all", () => {
    const log = vi.fn();
    expect(warnIfNoRoleClaim({}, log)).toBe(true);
    expect(log).toHaveBeenCalledTimes(1);
  });
  it("does not log again on a second call once it has already warned", () => {
    const log = vi.fn();
    warnIfNoRoleClaim({}, log);
    warnIfNoRoleClaim({}, log);
    expect(log).toHaveBeenCalledTimes(1);
  });
  it("logs when hasura_default_role is present but hasura_allowed_roles is absent", () => {
    const log = vi.fn();
    warnIfNoRoleClaim({ hasura_default_role: "x" }, log);
    expect(log).toHaveBeenCalled();
  });
  it("does not log when hasura_allowed_roles is present", () => {
    const log = vi.fn();
    expect(warnIfNoRoleClaim({ hasura_allowed_roles: ["a"] }, log)).toBe(false);
    expect(log).not.toHaveBeenCalled();
  });
  it("logs when hasura_allowed_roles is present but empty", () => {
    const log = vi.fn();
    warnIfNoRoleClaim({ hasura_allowed_roles: [] }, log);
    expect(log).toHaveBeenCalledTimes(1);
  });
  it("names the emission set in the warning message", () => {
    const log = vi.fn();
    warnIfNoRoleClaim({}, log);
    const [message] = log.mock.calls[0];
    expect(String(message).toLowerCase()).toContain("emission set");
  });
  it("treats an undefined payload as claim-less (no session yet is not an error)", () => {
    const log = vi.fn();
    expect(warnIfNoRoleClaim(undefined, log)).toBe(true);
  });
});

describe("readRoles", () => {
  it("wraps a single string role in an array", () => {
    expect(readRoles({ hasura_allowed_roles: "site" })).toEqual(["site"]);
  });
  it("trims whitespace and drops empty entries", () => {
    expect(readRoles({ hasura_allowed_roles: [" a ", ""] })).toEqual(["a"]);
  });
  it("does not dedupe — duplicates pass through, trimmed", () => {
    expect(readRoles({ hasura_allowed_roles: ["a", "a", " b "] })).toEqual(["a", "a", "b"]);
  });
  it("drops whitespace-only entries the same as empty strings", () => {
    expect(readRoles({ hasura_allowed_roles: ["a", "   "] })).toEqual(["a"]);
  });
  it("drops non-string array members rather than throwing", () => {
    expect(readRoles({ hasura_allowed_roles: ["a", 123, null, undefined] as unknown })).toEqual(["a"]);
  });
  it("returns an empty array when hasura_allowed_roles is absent", () => {
    expect(readRoles({})).toEqual([]);
    expect(readRoles(undefined)).toEqual([]);
    expect(readRoles("not-an-object")).toEqual([]);
  });
});

describe("readDefaultRole", () => {
  it("returns the trimmed default role string, or undefined", () => {
    expect(readDefaultRole({ hasura_default_role: " site " })).toBe("site");
    expect(readDefaultRole({ hasura_default_role: 7 })).toBeUndefined();
    expect(readDefaultRole({})).toBeUndefined();
  });
});

describe("hasAnyRole", () => {
  it("throws when the required argument is an empty array", () => {
    expect(() => hasAnyRole(["a"], [])).toThrow();
  });
  it("throws when the required argument is an empty string", () => {
    expect(() => hasAnyRole(["a"], "")).toThrow();
  });
  it("throws when the required argument holds only blank strings", () => {
    expect(() => hasAnyRole(["a"], [" ", ""])).toThrow();
  });
  it("is true when any required role is held, case-sensitively", () => {
    expect(hasAnyRole(["site", "office"], "office")).toBe(true);
    expect(hasAnyRole(["site"], ["Site"])).toBe(false);
    expect(hasAnyRole([], "site")).toBe(false);
  });
});
