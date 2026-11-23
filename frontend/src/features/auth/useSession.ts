/**
 * Session hooks: the single source of "who is signed in and as which organization".
 *
 * `useSession` drives the protected route (401 -> redirect to /login). Switching
 * organizations invalidates the session AND all tenant-scoped queries, so every
 * screen refetches under the new organization (no stale cross-tenant data).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { authApi } from "../../lib/api";

export const SESSION_QUERY_KEY = ["session"] as const;

export function useSession() {
  return useQuery({
    queryKey: SESSION_QUERY_KEY,
    queryFn: ({ signal }) => authApi.me(signal),
    // A closed session is a normal state (first visit), not an error to retry.
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => authApi.logout(),
    onSuccess: () => {
      void queryClient.invalidateQueries();
    },
  });
}

export function useSwitchOrganization() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (organizationId: string) => authApi.switchOrganization(organizationId),
    // The active org changed: the session AND every tenant-scoped list refetch.
    onSuccess: () => {
      void queryClient.invalidateQueries();
    },
  });
}
