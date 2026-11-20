"use server";

import { redirect } from "next/navigation";

import type { Organization } from "@/lib/api-types";
import { backendFetch, SignedOutError } from "@/lib/backend";
import { slugify } from "@/lib/slug";

export type CreateOrganizationState = {
  error?: "invalid" | "signedOut" | "unavailable";
  name?: string;
};

const ATTEMPTS = 3;

/**
 * Creates an organization with the signed-in person as its owner, then
 * opens the assistant in it. The technical name comes from the name; if it
 * is taken, a short random ending is added (the name itself may repeat).
 */
export async function createOrganization(
  _previous: CreateOrganizationState,
  form: FormData,
): Promise<CreateOrganizationState> {
  const name = String(form.get("name") ?? "").trim().replace(/\s+/g, " ");
  if (name.length < 2 || name.length > 150) return { error: "invalid", name };

  const base = slugify(name);
  let created: Organization | null = null;
  try {
    for (let attempt = 0; attempt < ATTEMPTS && !created; attempt += 1) {
      const slug = attempt === 0 ? base : `${base}-${crypto.randomUUID().slice(0, 6)}`;
      const response = await backendFetch("/organizations/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, slug }),
      });
      if (response.status === 409) continue;
      if (response.status === 401) return { error: "signedOut", name };
      if (response.status === 400 || response.status === 422) return { error: "invalid", name };
      if (!response.ok) return { error: "unavailable", name };
      created = (await response.json()) as Organization;
    }
  } catch (error) {
    return { error: error instanceof SignedOutError ? "signedOut" : "unavailable", name };
  }
  if (!created) return { error: "unavailable", name };
  redirect(`/assistente?org=${created.id}`);
}
