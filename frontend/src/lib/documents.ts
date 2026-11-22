import "server-only";

import type { Connection, DocumentItem, Upload } from "@/lib/api-types";
import { backendFetch } from "@/lib/backend";
import { DRIVE_PROVIDER, UPLOAD_PROVIDER } from "@/lib/uploads";

export type DocumentsData = {
  documents: DocumentItem[];
  /** Owners and admins manage sources; members also send files. */
  canManage: boolean;
  /** Owners, admins and members send files; viewers only read. */
  canUpload: boolean;
  /** Files sent but not yet read by the worker. */
  waiting: Upload[];
  lastError: string | null;
  /** The Google Drive source, for owners and admins; null when not connected. */
  drive: Connection | null;
};

/** The upload source of an organization, if it has one. */
export function uploadSource(connections: Connection[]): Connection | undefined {
  return connections.find((c) => c.provider === UPLOAD_PROVIDER && !c.disconnected_at);
}

/** The Google Drive source of an organization, if it has one. */
export function driveSource(connections: Connection[]): Connection | undefined {
  return connections.find((c) => c.provider === DRIVE_PROVIDER && !c.disconnected_at);
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
    // Not a manager. A member may still send files: their own waiting
    // uploads come from the upload source, if there is one yet.
    const own = await backendFetch(`/organizations/${organizationId}/upload-source`);
    const canUpload = own.ok || own.status === 404;
    const base = { documents, canManage: false, canUpload, waiting: [], lastError: null, drive: null };
    if (!own.ok) return base;
    return { ...base, ...(await waitingUploads(organizationId, (await own.json()) as Connection)) };
  }
  const connections = (await connectionsResponse.json()) as Connection[];
  const drive = driveSource(connections) ?? null;
  const source = uploadSource(connections);
  const manager = { documents, canManage: true, canUpload: true, waiting: [], lastError: null, drive };
  if (!source) return manager;
  return { ...manager, ...(await waitingUploads(organizationId, source)) };
}

/** The caller's own files not yet read, and the source's last failure. */
async function waitingUploads(
  organizationId: string,
  source: Connection,
): Promise<Pick<DocumentsData, "waiting" | "lastError">> {
  const uploadsResponse = await backendFetch(
    `/organizations/${organizationId}/connections/${source.id}/uploads/`,
  );
  const uploads = uploadsResponse.ok ? ((await uploadsResponse.json()) as Upload[]) : [];
  const syncedAt = source.last_synced_at ? Date.parse(source.last_synced_at) : 0;
  return {
    waiting: uploads.filter((upload) => Date.parse(upload.created_at) > syncedAt),
    lastError: source.last_error,
  };
}
