import "server-only";

import type { Invitation, Member } from "@/lib/api-types";
import { backendFetch } from "@/lib/backend";

export type PeopleData = { members: Member[]; invitations: Invitation[] };

/** Active members and pending invitations. Owners and admins only. */
export async function loadPeople(organizationId: string): Promise<PeopleData | null> {
  const base = `/organizations/${organizationId}`;
  let responses: [Response, Response];
  try {
    responses = await Promise.all([
      backendFetch(`${base}/users/?limit=100`),
      backendFetch(`${base}/invitations/`),
    ]);
  } catch {
    return null;
  }
  const [users, invitations] = responses;
  if (!users.ok || !invitations.ok) return null;
  const members = ((await users.json()) as Member[]).filter(
    (member) => member.membership.is_active && member.is_active,
  );
  return { members, invitations: (await invitations.json()) as Invitation[] };
}
