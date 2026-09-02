// Failure-mode tests (blueprint jwt-release-0.4, tests.md § Failure Mode Tests, CF-6/EC-10)
// against the React GraphQL helper, using an injected fake UserManager.
import { describe, it, expect, vi } from "vitest";
import { graphqlAuthHeadersFrom } from "../../../../../reference/react-oidc/auth/graphqlAuth";

const fresh = { expired: false, id_token: "fresh-id", access_token: "fresh-access", profile: { hasura_allowed_roles: ["site"] } };

describe("graphqlAuthHeadersFrom", () => {
  it("sends the ID token of a non-expired session", async () => {
    const um = { getUser: vi.fn().mockResolvedValue(fresh), signinSilent: vi.fn() };
    expect(await graphqlAuthHeadersFrom(um as never)).toEqual({ Authorization: "Bearer fresh-id" });
    expect(um.signinSilent).not.toHaveBeenCalled();
  });
  it("renews an expired session once and sends the renewed token", async () => {
    const um = {
      getUser: vi.fn().mockResolvedValue({ ...fresh, expired: true, id_token: "stale" }),
      signinSilent: vi.fn().mockResolvedValue(fresh),
    };
    expect(await graphqlAuthHeadersFrom(um as never)).toEqual({ Authorization: "Bearer fresh-id" });
    expect(um.signinSilent).toHaveBeenCalledTimes(1);
  });
  it("returns no Authorization header rather than a stale one when silent renew fails", async () => {
    const um = {
      getUser: vi.fn().mockResolvedValue({ ...fresh, expired: true, id_token: "stale" }),
      signinSilent: vi.fn().mockRejectedValue(new Error("blocked third-party cookies")),
    };
    const headers = await graphqlAuthHeadersFrom(um as never);
    expect(um.signinSilent).toHaveBeenCalled();
    expect(headers).not.toHaveProperty("Authorization");
  });
  it("shares ONE in-flight renewal across concurrent expired callers (EC-10)", async () => {
    let resolve!: (u: unknown) => void;
    const pending = new Promise((r) => (resolve = r));
    const um = {
      getUser: vi.fn().mockResolvedValue({ ...fresh, expired: true }),
      signinSilent: vi.fn().mockReturnValue(pending),
    };
    const calls = Promise.all([graphqlAuthHeadersFrom(um as never), graphqlAuthHeadersFrom(um as never), graphqlAuthHeadersFrom(um as never)]);
    resolve(fresh);
    const results = await calls;
    expect(um.signinSilent).toHaveBeenCalledTimes(1);
    for (const h of results) expect(h).toEqual({ Authorization: "Bearer fresh-id" });
  });
  it("returns {} with no session", async () => {
    const um = { getUser: vi.fn().mockResolvedValue(null), signinSilent: vi.fn().mockResolvedValue(null) };
    expect(await graphqlAuthHeadersFrom(um as never)).toEqual({});
  });
});
