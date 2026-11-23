/**
 * App-wide providers: the TanStack Query cache.
 *
 * Retry policy: never retry a 4xx (the answer will not change and retrying a 401
 * only delays the redirect to /login); one quiet retry for transient network/5xx
 * failures so a Neon cold start does not flash an error at the user.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { ApiError } from "../lib/api";

function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 1;
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: shouldRetry,
            // Server state is refetched on window focus; keep values fresh enough
            // for the shell to feel live without hammering a scale-to-zero DB.
            staleTime: 30_000,
            refetchOnWindowFocus: true,
          },
          mutations: { retry: false },
        },
      }),
  );
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
