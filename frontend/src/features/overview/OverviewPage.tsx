/**
 * Overview: the current organization and its workspaces, all REAL data from the
 * session-authenticated Phase 1 endpoints. Loading, empty and error states are
 * explicit — no mock data is ever rendered (Phase 2 exit gate).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button, TextField } from "../../components/ui/Controls";
import { Card, EmptyState, ErrorState, PageHeader, StatusBadge } from "../../components/ui/Feedback";
import { ApiError, tenantApi } from "../../lib/api";
import { useSession } from "../auth/useSession";

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

export function OverviewPage() {
  const session = useSession();
  const organization = useQuery({
    queryKey: ["organization"],
    queryFn: ({ signal }) => tenantApi.currentOrganization(signal),
  });
  const workspaces = useQuery({
    queryKey: ["workspaces"],
    queryFn: ({ signal }) => tenantApi.workspaces(signal),
  });
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [formMessage, setFormMessage] = useState<string | null>(null);

  const createWorkspace = useMutation({
    mutationFn: () => tenantApi.createWorkspace(name),
    onSuccess: async () => {
      setName("");
      setFormMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
    onError: (error: unknown) => {
      setFormMessage(messageOf(error));
    },
  });

  if (organization.isPending || workspaces.isPending) {
    return <p role="status">Loading your organization…</p>;
  }
  if (organization.isError) {
    return <ErrorState message={messageOf(organization.error)} onRetry={() => void organization.refetch()} />;
  }

  const org = organization.data;
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title={org.display_name}
        subtitle={
          org.default_market !== null
            ? `Market ${org.default_market} · ${org.timezone} · ${org.base_currency}`
            : `${org.timezone} · ${org.base_currency}`
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <p className="text-sm text-ink-400">Signed in as</p>
          <p className="mt-1 truncate font-medium text-ink-50">{session.data?.user.email ?? "…"}</p>
        </Card>
        <Card>
          <p className="text-sm text-ink-400">Organization</p>
          <p className="mt-1 font-medium text-ink-50">
            {org.display_name}{" "}
            {org.is_demo && <StatusBadge tone="info" label="demo" />}
          </p>
          <p className="text-xs text-ink-400">/{org.slug}</p>
        </Card>
        <Card>
          <p className="text-sm text-ink-400">Workspaces</p>
          <p className="mt-1 font-medium text-ink-50">{workspaces.data?.length ?? 0}</p>
        </Card>
      </div>

      <h2 className="mb-3 mt-8 text-lg font-semibold text-ink-50">Workspaces</h2>
      {workspaces.isError ? (
        <ErrorState message={messageOf(workspaces.error)} onRetry={() => void workspaces.refetch()} />
      ) : workspaces.data.length === 0 ? (
        <EmptyState title="No workspaces yet" hint="Create your first workspace below to get started." />
      ) : (
        <div className="overflow-hidden rounded-card border border-navy-700">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Workspaces in this organization</caption>
            <thead className="bg-navy-850 text-ink-400">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Name</th>
                <th scope="col" className="px-4 py-2 font-medium">Status</th>
                <th scope="col" className="px-4 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-700">
              {workspaces.data.map((workspace) => (
                <tr key={workspace.id} className="hover:bg-navy-850">
                  <td className="px-4 py-2 text-ink-50">{workspace.name}</td>
                  <td className="px-4 py-2">
                    <StatusBadge
                      tone={workspace.is_read_only ? "warn" : "ok"}
                      label={workspace.is_read_only ? "read-only" : "active"}
                    />
                  </td>
                  <td className="px-4 py-2 text-ink-400">
                    {new Date(workspace.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Card className="mt-6">
        <h3 className="font-medium text-ink-50">Create a workspace</h3>
        <form
          className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-start"
          onSubmit={(event) => {
            event.preventDefault();
            createWorkspace.mutate();
          }}
        >
          <div className="flex-1">
            <TextField
              id="workspace-name"
              label="Workspace name"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
              maxLength={100}
              required
            />
          </div>
          <div className="sm:pt-6">
            <Button type="submit" disabled={name.trim() === "" || createWorkspace.isPending}>
              {createWorkspace.isPending ? "Creating…" : "Create"}
            </Button>
          </div>
        </form>
        {formMessage !== null && (
          <p role="alert" className="mt-2 text-sm text-status-error">
            {formMessage}
          </p>
        )}
      </Card>
    </div>
  );
}
