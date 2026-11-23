/**
 * The authenticated application shell (blueprint 13.1, 13.10): sidebar navigation,
 * workspace (organization) selector, user menu with sign-out.
 *
 * Responsive: under 768px the sidebar becomes an off-canvas menu behind a top-bar
 * button (aria-expanded, Escape to close). The skip link is the first tab stop on
 * every page. Navigation uses semantic landmarks so screen readers can jump.
 */

import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useLogout, useSession, useSwitchOrganization } from "../features/auth/useSession";

interface NavItem {
  to: string;
  label: string;
  end: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", end: true },
  { to: "/members", label: "Members", end: false },
  { to: "/status", label: "System status", end: false },
];

function classNames(...parts: Array<string | false>): string {
  return parts.filter(Boolean).join(" ");
}

export function AppShell() {
  const session = useSession();
  const logout = useLogout();
  const switchOrg = useSwitchOrganization();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const navRef = useRef<HTMLElement>(null);

  // Escape closes the mobile menu; focus returns to the toggle button.
  useEffect(() => {
    if (!menuOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  const me = session.data;
  const memberships = me?.memberships ?? [];
  const active = me?.active_organization ?? null;

  function onSwitchOrg(organizationId: string) {
    if (organizationId === "") return;
    switchOrg.mutate(organizationId);
  }

  function onLogout() {
    logout.mutate(undefined, {
      onSuccess: () => {
        void navigate("/login", { replace: true });
      },
    });
  }

  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>

      {/* Mobile top bar */}
      <header className="flex items-center justify-between border-b border-navy-700 bg-navy-900 px-4 py-3 md:hidden">
        <span className="font-semibold tracking-wide text-gold-400">MarketPulse AI</span>
        <button
          ref={menuButtonRef}
          type="button"
          className="rounded-md border border-navy-600 px-3 py-1.5 text-ink-200"
          aria-expanded={menuOpen}
          aria-controls="app-sidebar"
          onClick={() => {
            setMenuOpen((open) => !open);
          }}
        >
          {menuOpen ? "Close menu" : "Open menu"}
        </button>
      </header>

      {/* Sidebar (off-canvas on mobile) */}
      <aside
        id="app-sidebar"
        ref={navRef}
        className={classNames(
          "border-navy-700 bg-navy-900 md:sticky md:top-0 md:flex md:h-dvh md:w-64 md:flex-col md:border-r",
          menuOpen ? "block" : "hidden md:flex",
        )}
      >
        <div className="hidden px-5 pb-2 pt-6 md:block">
          <span className="text-lg font-semibold tracking-wide text-gold-400">MarketPulse AI</span>
          <p className="text-sm text-ink-400">Know the market. Anticipate the move.</p>
        </div>

        <nav aria-label="Main navigation" className="px-3 py-3">
          <ul className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    classNames(
                      "block rounded-md px-3 py-2 text-sm",
                      isActive
                        ? "bg-navy-700 font-semibold text-gold-300"
                        : "text-ink-200 hover:bg-navy-800",
                    )
                  }
                  onClick={() => {
                    setMenuOpen(false);
                  }}
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="mt-auto space-y-3 border-t border-navy-700 px-4 py-4">
          <label className="block text-xs font-medium uppercase tracking-wide text-ink-400">
            Organization
            <select
              className="mt-1 w-full rounded-md border border-navy-600 bg-navy-800 px-2 py-2 text-sm text-ink-50"
              value={active?.id ?? ""}
              onChange={(event) => {
                onSwitchOrg(event.target.value);
              }}
              disabled={memberships.length < 2 || switchOrg.isPending}
            >
              {memberships.length === 0 && <option value="">No organization</option>}
              {memberships.map((membership) => (
                <option key={membership.organization_id} value={membership.organization_id}>
                  {membership.display_name} ({membership.role})
                </option>
              ))}
            </select>
          </label>

          <p className="truncate text-sm text-ink-200" title={me?.user.email ?? ""}>
            {me?.user.email ?? "…"}
          </p>
          <button
            type="button"
            className="w-full rounded-md border border-navy-600 px-3 py-2 text-sm text-ink-200 hover:bg-navy-800 disabled:opacity-60"
            onClick={onLogout}
            disabled={logout.isPending}
          >
            {logout.isPending ? "Signing out…" : "Sign out"}
          </button>
        </div>
      </aside>

      <main id="main-content" className="min-w-0 flex-1 px-4 py-6 md:px-8">
        <Outlet />
      </main>
    </div>
  );
}
