"use server";

import { revalidatePath } from "next/cache";

import type { Invitation } from "@/lib/api-types";
import { backendFetch, SignedOutError } from "@/lib/backend";
import { ROLES } from "@/lib/roles";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export type PeopleError =
  | "invalidEmail"
  | "pending"
  | "forbidden"
  | "lastOwner"
  | "gone"
  | "signedOut"
  | "unavailable";

export type InviteState = {
  error?: PeopleError;
  /** The invitation just sent, and its token while e-mails are not delivered. */
  invited?: { email: string; token: string | null };
  /** What the person typed, kept when something fails. */
  email?: string;
};

export type ChangeState = { error?: PeopleError; done?: boolean };

function failure(status: number, conflict: PeopleError): PeopleError {
  if (status === 401) return "signedOut";
  if (status === 403) return "forbidden";
  if (status === 404) return "gone";
  if (status === 409) return conflict;
  if (status === 422) return "invalidEmail";
  return "unavailable";
}

async function call(path: string, init: RequestInit): Promise<Response | PeopleError> {
  try {
    return await backendFetch(path, init);
  } catch (error) {
    return error instanceof SignedOutError ? "signedOut" : "unavailable";
  }
}

function role(form: FormData): string {
  const value = String(form.get("role") ?? "member");
  return (ROLES as string[]).includes(value) ? value : "";
}

/** Invites someone by e-mail, with a role. */
export async function invitePerson(_previous: InviteState, form: FormData): Promise<InviteState> {
  const organizationId = String(form.get("organizationId") ?? "");
  const email = String(form.get("email") ?? "").trim().toLowerCase();
  const chosen = role(form);
  if (!UUID.test(organizationId) || !chosen) return { error: "unavailable", email };
  if (!EMAIL.test(email) || email.length > 254) return { error: "invalidEmail", email };

  const response = await call(`/organizations/${organizationId}/invitations/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, role: chosen }),
  });
  if (typeof response === "string") return { error: response, email };
  if (!response.ok) return { error: failure(response.status, "pending"), email };
  const invitation = (await response.json()) as Invitation;
  revalidatePath("/pessoas");
  return { invited: { email: invitation.email, token: invitation.token ?? null } };
}

/** Gives a member another role. */
export async function changeRole(_previous: ChangeState, form: FormData): Promise<ChangeState> {
  const organizationId = String(form.get("organizationId") ?? "");
  const userId = String(form.get("userId") ?? "");
  const chosen = role(form);
  if (!UUID.test(organizationId) || !UUID.test(userId) || !chosen) return { error: "unavailable" };

  const response = await call(`/organizations/${organizationId}/users/${userId}/membership`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role: chosen }),
  });
  if (typeof response === "string") return { error: response };
  if (!response.ok) return { error: failure(response.status, "lastOwner") };
  revalidatePath("/pessoas");
  return { done: true };
}

/** Removes a member: they lose access at once. */
export async function removePerson(_previous: ChangeState, form: FormData): Promise<ChangeState> {
  const organizationId = String(form.get("organizationId") ?? "");
  const userId = String(form.get("userId") ?? "");
  if (!UUID.test(organizationId) || !UUID.test(userId)) return { error: "unavailable" };

  const response = await call(`/organizations/${organizationId}/users/${userId}`, { method: "DELETE" });
  if (typeof response === "string") return { error: response };
  if (!response.ok) return { error: failure(response.status, "lastOwner") };
  revalidatePath("/pessoas");
  return { done: true };
}

/** Cancels an invitation that was not accepted yet. */
export async function revokeInvitation(_previous: ChangeState, form: FormData): Promise<ChangeState> {
  const organizationId = String(form.get("organizationId") ?? "");
  const invitationId = String(form.get("invitationId") ?? "");
  if (!UUID.test(organizationId) || !UUID.test(invitationId)) return { error: "unavailable" };

  const response = await call(`/organizations/${organizationId}/invitations/${invitationId}`, {
    method: "DELETE",
  });
  if (typeof response === "string") return { error: response };
  // Already gone is what the person wanted.
  if (!response.ok && response.status !== 404) return { error: failure(response.status, "unavailable") };
  revalidatePath("/pessoas");
  return { done: true };
}
