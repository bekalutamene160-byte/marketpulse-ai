/**
 * API client tests: the error envelope contract, CSRF header attachment, and
 * credential sending — the three behaviors every screen depends on.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, authApi, apiFetch } from "./api";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("apiFetch", () => {
  beforeEach(() => {
    document.cookie = "mp_csrf=csrf-value; path=/";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = "mp_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("parses the stable error envelope into ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          json(
            { error: { code: "UNAUTHORIZED", message: "Email or password is incorrect.", request_id: "abc" } },
            401,
          ),
        ),
      ),
    );
    const error = await apiFetch("/api/v1/auth/login", { method: "POST", body: {} }).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.code).toBe("UNAUTHORIZED");
    expect(apiError.message).toBe("Email or password is incorrect.");
    expect(apiError.status).toBe(401);
    expect(apiError.requestId).toBe("abc");
  });

  it("attaches the CSRF header on state-changing requests", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      return Promise.resolve(json({ ok: true, url, init }));
    });
    vi.stubGlobal("fetch", fetchMock);

    await authApi.logout();
    const init = fetchMock.mock.calls[0]?.[1];
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("csrf-value");
    expect(init?.credentials).toBe("include");
  });

  it("does NOT attach a CSRF header to reads", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      return Promise.resolve(json({ ok: true, url, init }));
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/health/live");
    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.headers).toEqual({});
  });

  it("turns a network failure into an honest NETWORK error", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    const error = await apiFetch("/api/v1/health/live").catch((e: unknown) => e);
    expect((error as ApiError).code).toBe("NETWORK");
    expect((error as ApiError).message).toContain("Could not reach the API");
  });
});

describe("authApi.me", () => {
  it("returns the parsed session payload", async () => {
    const payload = {
      user: { id: "u1", email: "a@b.c", created_at: "2026-01-01T00:00:00Z" },
      active_organization: { id: "o1", slug: "acme", display_name: "Acme", is_demo: false },
      memberships: [{ organization_id: "o1", slug: "acme", display_name: "Acme", role: "owner" }],
    };
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json(payload))));
    const me = await authApi.me();
    expect(me.user.email).toBe("a@b.c");
    expect(me.memberships).toHaveLength(1);
  });
});
