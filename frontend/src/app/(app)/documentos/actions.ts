"use server";

import { redirect } from "next/navigation";

import type { Connection } from "@/lib/api-types";
import { backendFetch } from "@/lib/backend";
import { driveSource } from "@/lib/documents";
import { DRIVE_PROVIDER } from "@/lib/uploads";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const GOOGLE = "https://accounts.google.com/";

export type SourceActionState = {
  error?: "notConfigured" | "forbidden" | "unavailable";
  /** The sync was queued. */
  done?: boolean;
};

function failure(status: number): SourceActionState {
  if (status === 503) return { error: "notConfigured" };
  if (status === 401 || status === 403) return { error: "forbidden" };
  return { error: "unavailable" };
}

/**
 * Opens Google's consent page for this organization's Drive source,
 * creating the source the first time. The address comes from the backend
 * (signed state, PKCE); only a Google address is followed.
 */
export async function connectGoogleDrive(
  _previous: SourceActionState,
  form: FormData,
): Promise<SourceActionState> {
  const organizationId = String(form.get("organizationId") ?? "");
  if (!UUID.test(organizationId)) return { error: "unavailable" };
  const base = `/organizations/${organizationId}/connections/`;

  let url: string;
  try {
    const list = await backendFetch(base);
    if (!list.ok) return failure(list.status);
    let drive = driveSource((await list.json()) as Connection[]);
    if (!drive) {
      const created = await backendFetch(base, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: DRIVE_PROVIDER, name: "Google Drive", settings: {} }),
      });
      if (!created.ok) return failure(created.status);
      drive = (await created.json()) as Connection;
    }
    const started = await backendFetch(`${base}${drive.id}/google/authorize`, { method: "POST" });
    if (!started.ok) return failure(started.status);
    url = ((await started.json()) as { authorization_url: string }).authorization_url;
  } catch {
    return { error: "unavailable" };
  }
  if (!url.startsWith(GOOGLE)) return { error: "unavailable" };
  redirect(url);
}

/** Asks the worker to read the source again. */
export async function syncSource(
  _previous: SourceActionState,
  form: FormData,
): Promise<SourceActionState> {
  const organizationId = String(form.get("organizationId") ?? "");
  const connectionId = String(form.get("connectionId") ?? "");
  if (!UUID.test(organizationId) || !UUID.test(connectionId)) return { error: "unavailable" };
  try {
    const response = await backendFetch(
      `/organizations/${organizationId}/connections/${connectionId}/sync`,
      { method: "POST" },
    );
    return response.ok ? { done: true } : failure(response.status);
  } catch {
    return { error: "unavailable" };
  }
}
