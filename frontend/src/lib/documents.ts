import "server-only";

import type { Colleague, Connection, DocumentItem, DocumentPage, Upload } from "@/lib/api-types";
import { backendFetch } from "@/lib/backend";
import { DRIVE_PROVIDER, UPLOAD_PROVIDER } from "@/lib/uploads";

export type DocumentsData = {
  documents: DocumentItem[];
  /** Owners and admins manage sources; members also send files. */
  canManage: boolean;
  /** Owners, admins and members send files; viewers only read. */
  canUpload: boolean;
  /** Who a file can be shared with: active colleagues, names only. */
  colleagues: Colleague[];
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

/** Colleagues a file can be shared with; empty for viewers. */
async function loadColleagues(organizationId: string): Promise<Colleague[]> {
  const response = await backendFetch(`/organizations/${organizationId}/directory/?limit=100`);
  return response.ok ? ((await response.json()) as Colleague[]) : [];
}

export async function loadDocuments(organizationId: string): Promise<DocumentsData | null> {
  const data = await loadSources(organizationId);
  if (!data) return null;
  return { ...data, colleagues: data.canUpload ? await loadColleagues(organizationId) : [] };
}

async function loadSources(organizationId: string): Promise<Omit<DocumentsData, "colleagues"> | null> {
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

/** A document for its page, "missing" when the caller cannot open it (or it
 *  does not exist: they look the same), null when the backend is down. */
export async function loadDocumentPage(
  organizationId: string,
  documentId: string,
): Promise<DocumentPage | "missing" | null> {
  try {
    const response = await backendFetch(`/organizations/${organizationId}/documents/${documentId}/page`);
    if (response.status === 404 || response.status === 422) return "missing";
    return response.ok ? ((await response.json()) as DocumentPage) : null;
  } catch {
    return null;
  }
}
