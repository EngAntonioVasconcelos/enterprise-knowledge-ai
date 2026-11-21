"use server";

import { revalidatePath } from "next/cache";

import { RETENTION_DAYS } from "@/lib/api-types";
import { backendFetch, SignedOutError } from "@/lib/backend";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type SettingsState = {
  error?: "invalidName" | "forbidden" | "signedOut" | "unavailable";
  saved?: boolean;
};

/** Saves what changed: the name, and how long questions are kept. */
export async function saveSettings(_previous: SettingsState, form: FormData): Promise<SettingsState> {
  const organizationId = String(form.get("organizationId") ?? "");
  if (!UUID.test(organizationId)) return { error: "unavailable" };

  const name = String(form.get("name") ?? "").trim().replace(/\s+/g, " ");
  const retention = Number(form.get("retention"));
  const changes: Record<string, unknown> = {};
  if (name !== String(form.get("currentName") ?? "")) {
    if (name.length < 2 || name.length > 150) return { error: "invalidName" };
    changes.name = name;
  }
  if (String(retention) !== String(form.get("currentRetention") ?? "")) {
    if (!(RETENTION_DAYS as readonly number[]).includes(retention)) return { error: "unavailable" };
    changes.history_retention_days = retention;
  }
  if (!Object.keys(changes).length) return { saved: true };

  try {
    const response = await backendFetch(`/organizations/${organizationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    });
    if (response.status === 401) return { error: "signedOut" };
    if (response.status === 403) return { error: "forbidden" };
    if (response.status === 422) return { error: "invalidName" };
    if (!response.ok) return { error: "unavailable" };
  } catch (error) {
    return { error: error instanceof SignedOutError ? "signedOut" : "unavailable" };
  }
  revalidatePath("/", "layout");
  return { saved: true };
}
