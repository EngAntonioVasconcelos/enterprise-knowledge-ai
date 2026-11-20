import "server-only";

import type { Connection, DocumentItem, Upload } from "@/lib/api-types";
import { backendFetch } from "@/lib/backend";
import { UPLOAD_PROVIDER } from "@/lib/uploads";

export type DocumentsData = {
  documents: DocumentItem[];
  /** Owners and admins add and manage documents; others read the list. */
  canManage: boolean;
  /** Files sent but not yet read by the worker. */
  waiting: Upload[];
  lastError: string | null;
};

/** The upload source of an organization, if it has one. */
export function uploadSource(connections: Connection[]): Connection | undefined {
  return connections.find((c) => c.provider === UPLOAD_PROVIDER && !c.disconnected_at);
}

export async function loadDocuments(organizationId: string): Promise<DocumentsData | null> {
  const [documentsResponse, connectionsResponse] = await Promise.all([
    backendFetch(`/organizations/${organizationId}/documents/`),
    backendFetch(`/organizations/${organizationId}/connections/`),
  ]);
  if (!documentsResponse.ok) return null;
  const documents = ((await documentsResponse.json()) as DocumentItem[]).filter(
    (document) => document.status !== "removed",
  );

  if (!connectionsResponse.ok) {
    return { documents, canManage: false, waiting: [], lastError: null };
  }
  const source = uploadSource((await connectionsResponse.json()) as Connection[]);
  if (!source) return { documents, canManage: true, waiting: [], lastError: null };

  const uploadsResponse = await backendFetch(
    `/organizations/${organizationId}/connections/${source.id}/uploads/`,
  );
  const uploads = uploadsResponse.ok ? ((await uploadsResponse.json()) as Upload[]) : [];
  const syncedAt = source.last_synced_at ? Date.parse(source.last_synced_at) : 0;
  return {
    documents,
    canManage: true,
    waiting: uploads.filter((upload) => Date.parse(upload.created_at) > syncedAt),
    lastError: source.last_error,
  };
}
