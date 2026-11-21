"use server";

import { revalidatePath } from "next/cache";

import { backendFetch } from "@/lib/backend";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type HistoryActionState = { error?: "unavailable"; done?: boolean };

/** Deletes one of the person's questions, or all of them when no id is given. */
export async function deleteQuestions(
  _previous: HistoryActionState,
  form: FormData,
): Promise<HistoryActionState> {
  const organizationId = String(form.get("organizationId") ?? "");
  const entryId = String(form.get("entryId") ?? "");
  if (!UUID.test(organizationId) || (entryId && !UUID.test(entryId))) return { error: "unavailable" };
  try {
    const response = await backendFetch(`/organizations/${organizationId}/history/${entryId}`, {
      method: "DELETE",
    });
    // Already gone is what the person wanted.
    if (!response.ok && response.status !== 404) return { error: "unavailable" };
  } catch {
    return { error: "unavailable" };
  }
  revalidatePath("/historico");
  return { done: true };
}
