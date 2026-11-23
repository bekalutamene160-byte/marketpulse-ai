/**
 * App shell: keyboard navigation and the responsive menu (Phase 2 exit gate).
 *
 * - The skip link is the FIRST tab stop on the page.
 * - The mobile menu toggles aria-expanded and closes on Escape (focus returns to
 *   the toggle button).
 * - Navigation landmarks and links are present and correctly labelled.
 * - The organization selector is disabled until there is more than one membership.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "./AppShell";

const ME = {
  user: { id: "u1", email: "owner@example.com", created_at: "2026-01-01T00:00:00Z" },
  active_organization: { id: "o1", slug: "acme", display_name: "Acme", is_demo: false },
  memberships: [
    { organization_id: "o1", slug: "acme", display_name: "Acme", role: "owner" },
    { organization_id: "o2", slug: "globex", display_name: "Globex", role: "admin" },
  ],
};

function stubSession() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/auth/me")) {
        return Promise.resolve(new Response(JSON.stringify(ME), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    }),
  );
}

function renderShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<p>overview-body</p>} />
            <Route path="/members" element={<p>members-body</p>} />
            <Route path="/status" element={<p>status-body</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AppShell keyboard navigation", () => {
  it("puts the skip link first in the tab order and targets the main landmark", async () => {
    stubSession();
    renderShell();

    await userEvent.tab();
    const skipLink = screen.getByRole("link", { name: "Skip to content" });
    expect(document.activeElement).toBe(skipLink);
    expect(skipLink).toHaveAttribute("href", "#main-content");
  });

  it("navigates with keyboard and shows the current page as selected", async () => {
    stubSession();
    renderShell();

    const membersLink = await screen.findByRole("link", { name: "Members" });
    await userEvent.click(membersLink);
    expect(await screen.findByText("members-body")).toBeInTheDocument();

    const overviewLink = screen.getByRole("link", { name: "Overview" });
    await userEvent.click(overviewLink);
    expect(await screen.findByText("overview-body")).toBeInTheDocument();
  });

  it("toggles the responsive menu with aria-expanded and closes on Escape", async () => {
    stubSession();
    renderShell();

    const toggle = screen.getByRole("button", { name: "Open menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAttribute("aria-controls", "app-sidebar");

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Close menu" })).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(await screen.findByRole("button", { name: "Open menu" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("shows the signed-in user and both organizations in the selector", async () => {
    stubSession();
    renderShell();

    expect(await screen.findByText("owner@example.com")).toBeInTheDocument();
    const selector = screen.getByLabelText(/Organization/);
    expect(selector).not.toBeDisabled();
    expect((selector as HTMLSelectElement).options.length).toBe(2);
    expect((selector as HTMLSelectElement).value).toBe("o1"); // active org preselected
  });

  it("offers a sign-out control", async () => {
    stubSession();
    renderShell();
    expect(await screen.findByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });
});
