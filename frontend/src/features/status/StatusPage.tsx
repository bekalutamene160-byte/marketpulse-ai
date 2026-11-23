/**
 * System status (the Phase 0 health page, preserved as a shell route).
 *
 * Shows the REAL liveness/readiness of the backend — honest operational
 * transparency, reachable from the sidebar. Readiness may be slow on a
 * scale-to-zero database; its failure never hides liveness.
 */

import { useEffect, useState } from "react";

import { fetchLive, fetchReady, type LiveResponse, type ReadyResponse } from "../../lib/api";
import { Card, PageHeader, StatusBadge } from "../../components/ui/Feedback";

type State =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "done"; live: LiveResponse; ready: ReadyResponse | null; readyError: string | null };

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

/** Pure data loading: returns the next UI state and never touches React state itself. */
async function loadStatus(signal?: AbortSignal): Promise<State> {
  try {
    const live = await fetchLive(signal);
    try {
      const ready = await fetchReady(signal);
      return { phase: "done", live, ready, readyError: null };
    } catch (error) {
      return { phase: "done", live, ready: null, readyError: messageOf(error, "Readiness check failed") };
    }
  } catch (error) {
    return { phase: "error", message: messageOf(error, "Could not reach the API") };
  }
}

export function StatusPage() {
  const [state, setState] = useState<State>({ phase: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    void loadStatus(controller.signal).then((next) => {
      // Ignore a result that arrives after unmount (StrictMode mounts effects twice in dev).
      if (!controller.signal.aborted) setState(next);
    });
    return () => {
      controller.abort();
    };
  }, []);

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="System status"
        subtitle="Liveness and readiness of the API, straight from the health endpoints."
      />

      {state.phase === "loading" && <p role="status">Checking the API…</p>}
      {state.phase === "error" && (
        <p role="alert">API unreachable: {state.message}. Is the backend running?</p>
      )}
      {state.phase === "done" && (
        <div className="flex flex-col gap-4">
          <Card>
            <p className="flex items-center gap-2 text-sm text-ink-400">
              API <StatusBadge tone="ok" label={state.live.status} />
            </p>
            <p className="mt-1 text-sm text-ink-200">
              v{state.live.version} · {state.live.environment}
            </p>
          </Card>
          {state.ready !== null && (
            <Card>
              <p className="text-sm text-ink-400">
                Readiness{" "}
                <StatusBadge
                  tone={state.ready.status === "ready" ? "ok" : "warn"}
                  label={state.ready.status === "ready" ? "ready" : "not ready"}
                />
              </p>
              <ul className="mt-2 space-y-1 text-sm text-ink-200">
                {Object.entries(state.ready.checks).map(([name, check]) => (
                  <li key={name}>
                    {name}: {check.status}
                    {check.latency_ms !== null && ` (${String(check.latency_ms)} ms)`}
                    {!check.required && " (optional)"}
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {state.readyError !== null && <p role="alert">Readiness unavailable: {state.readyError}</p>}
        </div>
      )}
    </div>
  );
}
