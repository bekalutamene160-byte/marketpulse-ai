/**
 * Members: the organization's member list, served by the RLS-secured
 * memberships→users join (Phase 2 backend). Loading, empty and error states are
 * explicit; invitations arrive in a later phase (no email adapter yet — ADR-012).
 */

import { useQuery } from "@tanstack/react-query";

import { Card, EmptyState, ErrorState, PageHeader, StatusBadge } from "../../components/ui/Feedback";
import { ApiError, tenantApi, type Member } from "../../lib/api";
import { useSession } from "../auth/useSession";

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

function roleTone(role: string): "ok" | "info" {
  return role === "owner" ? "ok" : "info";
}

function statusTone(status: string): "ok" | "warn" | "error" {
  if (status === "active") return "ok";
  if (status === "suspended") return "error";
  return "warn"; // invited and anything new
}

function MemberRow({ member }: { member: Member }) {
  return (
    <tr className="hover:bg-navy-850">
      <td className="px-4 py-2 text-ink-50">{member.email}</td>
      <td className="px-4 py-2">
        <StatusBadge tone={roleTone(member.role)} label={member.role} />
      </td>
      <td className="px-4 py-2">
        <StatusBadge tone={statusTone(member.status)} label={member.status} />
      </td>
      <td className="px-4 py-2 text-ink-400">{new Date(member.created_at).toLocaleDateString()}</td>
    </tr>
  );
}

export function MembersPage() {
  const session = useSession();
  const members = useQuery({
    queryKey: ["members"],
    queryFn: ({ signal }) => tenantApi.members(signal),
  });

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Members"
        subtitle={
          session.data?.active_organization !== null && session.data !== undefined
            ? `People with access to ${session.data.active_organization.display_name}.`
            : undefined
        }
      />

      {members.isPending ? (
        <p role="status">Loading members…</p>
      ) : members.isError ? (
        <ErrorState message={messageOf(members.error)} onRetry={() => void members.refetch()} />
      ) : members.data.length === 0 ? (
        <EmptyState title="No members yet" hint="The owner should appear here after signing up." />
      ) : (
        <Card className="overflow-hidden p-0">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Members of this organization</caption>
            <thead className="bg-navy-850 text-ink-400">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Email</th>
                <th scope="col" className="px-4 py-2 font-medium">Role</th>
                <th scope="col" className="px-4 py-2 font-medium">Status</th>
                <th scope="col" className="px-4 py-2 font-medium">Joined</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-700">
              {members.data.map((member) => (
                <MemberRow key={member.membership_id} member={member} />
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
