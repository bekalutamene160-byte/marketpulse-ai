/**
 * Protected route: renders the children only for a valid session.
 *
 * Loading shows a quiet spinner (no layout shift); an unauthorized session
 * redirects to /login and remembers where the user was going, so signing in
 * returns them to the same screen.
 */

import { Navigate, Outlet, useLocation } from "react-router-dom";

import { Spinner } from "../../components/ui/Spinner";
import { isUnauthorized } from "../../lib/api";
import { useSession } from "./useSession";

export function ProtectedRoute() {
  const session = useSession();
  const location = useLocation();

  if (session.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center" aria-busy="true">
        <Spinner label="Checking your session…" />
      </div>
    );
  }
  if (session.isError && isUnauthorized(session.error)) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  // Any other error (e.g. 503 while the database wakes up) is an honest error state.
  if (session.isError) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
        <p role="alert" className="text-ink-200">
          The service is not ready right now ({session.error instanceof Error ? session.error.message : "unknown error"}).
        </p>
        <button
          type="button"
          className="rounded-md bg-gold-500 px-4 py-2 font-medium text-navy-950 hover:bg-gold-400"
          onClick={() => void session.refetch()}
        >
          Try again
        </button>
      </div>
    );
  }
  return <Outlet />;
}
