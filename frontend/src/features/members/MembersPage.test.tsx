/** Members page: loading, data and error states on the RLS-secured member list. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MembersPage } from "./MembersPage";

const ME = {
  user: { id: "u1", email: "owner@example.com", created_at: "2026-01-01T00:00:00Z" },
  active_organization: { id: "o1", slug: "acme", display_name: "Acme", is_demo: false },
  memberships: [{ organization_id: "o1", slug: "acme", display_name: "Acme", role: "owner" }],
};

const MEMBERS = [
  {
    membership_id: "m1",
    user_id: "u1",
    email: "owner@example.com",
    role: "owner",
    status: "active",
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    membership_id: "m2",
    user_id: "u2",
    email: "analyst@example.com",
    role: "member",
    status: "invited",
    created_at: "2026-02-01T00:00:00Z",
  },
];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function stubRoutes(members: () => Promise<Response>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/auth/me")) return Promise.resolve(jsonResponse(ME));
      if (url.endsWith("/organizations/members")) return members();
      return Promise.reject(new Error(`unexpected request: ${url}`));
    }),
  );
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MembersPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("MembersPage", () => {
  it("shows the member list with roles and statuses as text + color", async () => {
    stubRoutes(() => Promise.resolve(jsonResponse(MEMBERS)));
    renderPage();

    expect(await screen.findByText("owner@example.com")).toBeInTheDocument();
    expect(screen.getByText("analyst@example.com")).toBeInTheDocument();
    // Statuses are readable text, never color-only.
    expect(screen.getAllByText("active").length).toBeGreaterThan(0);
    expect(screen.getByText("invited")).toBeInTheDocument();
    expect(screen.getByText("People with access to Acme.")).toBeInTheDocument();
  });

  it("shows an honest error state with retry", async () => {
    stubRoutes(() => Promise.resolve(jsonResponse({ error: { code: "UNAUTHORIZED", message: "Session expired.", request_id: "r" } }, 401)));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Session expired.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("renders a loading state first", () => {
    stubRoutes(() => new Promise<Response>(() => undefined));
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("Loading members…");
  });
});
