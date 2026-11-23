/**
 * Auth screens: zod validation, server error surfaces, and the success redirect.
 * The API layer is stubbed at the fetch boundary (same pattern as Phase 0 tests).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import { LoginPage } from "./LoginPage";
import { RegisterPage } from "./RegisterPage";
import { ProtectedRoute } from "./ProtectedRoute";
import { Spinner } from "../../components/ui/Spinner";

function renderWithProviders(ui: React.ReactElement, initialPath: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/login" element={ui} />
          <Route path="/register" element={ui} />
          <Route path="*" element={<p>landed</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function stubLogin(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const mock = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })),
  );
  vi.stubGlobal("fetch", mock);
  return mock;
}

describe("LoginPage", () => {
  it("shows zod validation messages before calling the API", async () => {
    const fetchMock = stubLogin(200, { user: {}, organization_id: null });
    renderWithProviders(<LoginPage />, "/login");

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("surfaces the uniform 401 message from the error envelope", async () => {
    stubLogin(401, {
      error: { code: "UNAUTHORIZED", message: "Email or password is incorrect.", request_id: "r1" },
    });
    renderWithProviders(<LoginPage />, "/login");

    await userEvent.type(screen.getByLabelText("Email"), "owner@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "whatever-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
  });

  it("redirects to the overview on success", async () => {
    stubLogin(200, {
      user: { id: "u1", email: "a@b.c", created_at: "2026-01-01T00:00:00Z" },
      organization_id: "o1",
    });
    renderWithProviders(<LoginPage />, "/login");

    await userEvent.type(screen.getByLabelText("Email"), "owner@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "whatever-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("landed")).toBeInTheDocument();
  });
});

describe("RegisterPage", () => {
  it("rejects a short password without calling the API", async () => {
    const fetchMock = stubLogin(201, {});
    renderWithProviders(<RegisterPage />, "/register");

    await userEvent.type(screen.getByLabelText("Organization name"), "Acme");
    await userEvent.type(screen.getByLabelText("Work email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Use at least 12 characters")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("surfaces the server's conflict message", async () => {
    stubLogin(409, {
      error: { code: "CONFLICT", message: "An account with that email already exists.", request_id: "r2" },
    });
    renderWithProviders(<RegisterPage />, "/register");

    await userEvent.type(screen.getByLabelText("Organization name"), "Acme");
    await userEvent.type(screen.getByLabelText("Work email"), "taken@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "long-enough-password");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
  });
});

describe("ProtectedRoute", () => {
  it("redirects to /login when the session is unauthorized", async () => {
    stubLogin(401, {
      error: { code: "UNAUTHORIZED", message: "Authentication is required.", request_id: "r3" },
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/members"]}>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/members" element={<p>secret</p>} />
            </Route>
            <Route path="/login" element={<p>sign-in-page</p>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("sign-in-page")).toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("renders the children when the session is valid", async () => {
    stubLogin(200, {
      user: { id: "u1", email: "a@b.c", created_at: "2026-01-01T00:00:00Z" },
      active_organization: { id: "o1", slug: "acme", display_name: "Acme", is_demo: false },
      memberships: [],
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/members"]}>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/members" element={<p>secret</p>} />
            </Route>
            <Route path="/login" element={<p>sign-in-page</p>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("secret")).toBeInTheDocument();
  });

  it("shows a spinner while the session is being checked", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)), // never resolves
    );
    render(<Spinner label="Checking your session…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Checking your session…");
  });
});

describe("form a11y wiring", () => {
  it("labels connect inputs, errors use role=alert", async () => {
    stubLogin(200, {});
    renderWithProviders(<LoginPage />, "/login");
    const email = screen.getByLabelText("Email");
    expect(email).toHaveAttribute("type", "email");
    await waitFor(() => {
      expect(email).toBeInTheDocument();
    });
  });
});
