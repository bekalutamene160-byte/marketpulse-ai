/**
 * Route table (blueprint 14.1 route groups, Phase 2 subset).
 *
 * /login and /register are public; everything under / requires a session
 * (ProtectedRoute redirects to /login and remembers the target). The catch-all
 * route keeps unknown URLs inside the shell instead of a blank page.
 */

import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "./AppShell";
import { LoginPage } from "../features/auth/LoginPage";
import { ProtectedRoute } from "../features/auth/ProtectedRoute";
import { RegisterPage } from "../features/auth/RegisterPage";
import { MembersPage } from "../features/members/MembersPage";
import { OverviewPage } from "../features/overview/OverviewPage";
import { StatusPage } from "../features/status/StatusPage";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, path: "/", element: <OverviewPage /> },
          { path: "members", element: <MembersPage /> },
          { path: "status", element: <StatusPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
