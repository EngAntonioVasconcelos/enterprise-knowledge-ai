"use server";

import type { Membership } from "@/lib/api-types";
import { backendFetch, SignedOutError } from "@/lib/backend";

export type AcceptState = {
  error?: "invalid" | "otherEmail" | "unverified" | "alreadyMember" | "signedOut" | "unavailable";
  /** The organization joined. */
  organizationId?: string;
};

const OTHER_EMAIL = "This invitation was sent to another email address.";

/** Accepts the invitation with its one-time token, as the signed-in person. */
export async function acceptInvitation(_previous: AcceptState, form: FormData): Promise<AcceptState> {
  const token = String(form.get("token") ?? "");
  if (token.length < 20 || token.length > 200) return { error: "invalid" };

  let response: Response;
  try {
    response = await backendFetch("/invitations/accept", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
  } catch (error) {
    return { error: error instanceof SignedOutError ? "signedOut" : "unavailable" };
  }
  if (response.ok) return { organizationId: ((await response.json()) as Membership).organization_id };
  if (response.status === 401) return { error: "signedOut" };
  if (response.status === 404 || response.status === 422) return { error: "invalid" };
  if (response.status === 409) return { error: "alreadyMember" };
  if (response.status === 403) {
    const detail = ((await response.json().catch(() => ({}))) as { detail?: unknown }).detail;
    return { error: detail === OTHER_EMAIL ? "otherEmail" : "unverified" };
  }
  return { error: "unavailable" };
}
