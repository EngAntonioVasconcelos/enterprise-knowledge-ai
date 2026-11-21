import "server-only";

import type { HistoryEntry, HistoryItem } from "@/lib/api-types";
import { backendFetch } from "@/lib/backend";

/** The signed-in person's own questions, newest first; null if unavailable. */
export async function loadHistory(organizationId: string, limit = 100): Promise<HistoryItem[] | null> {
  try {
    const response = await backendFetch(`/organizations/${organizationId}/history/?limit=${limit}`);
    return response.ok ? ((await response.json()) as HistoryItem[]) : null;
  } catch {
    return null;
  }
}

/** One entry; "missing" when it no longer exists (deleted or expired). */
export async function loadEntry(
  organizationId: string,
  entryId: string,
): Promise<HistoryEntry | "missing" | null> {
  try {
    const response = await backendFetch(`/organizations/${organizationId}/history/${entryId}`);
    if (response.status === 404 || response.status === 422) return "missing";
    return response.ok ? ((await response.json()) as HistoryEntry) : null;
  } catch {
    return null;
  }
}
