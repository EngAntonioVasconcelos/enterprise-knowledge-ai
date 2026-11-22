import { NextResponse } from "next/server";

import type { Connection } from "@/lib/api-types";
import { backendFetch, SignedOutError } from "@/lib/backend";
import { uploadSource } from "@/lib/documents";
import { checkFile, UPLOAD_PROVIDER, uploadErrorFromStatus, VISIBILITIES } from "@/lib/uploads";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function failed(error: string, status: number) {
  return NextResponse.json({ error }, { status });
}

// One file per request, sent on to the backend with the person's token.
// The upload source ("Uploaded files") is created on the first upload, so
// nobody has to set up a "connection" to send a PDF.
export async function POST(request: Request) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return failed("unsupported", 400);
  }
  const organizationId = form.get("organizationId");
  const sourceName = String(form.get("sourceName") ?? "").slice(0, 200) || "Uploaded files";
  const file = form.get("file");
  // Who reads the file: what the person chose; when unsaid, only them.
  const chosen = String(form.get("visibility") ?? "");
  const visibility = (VISIBILITIES as readonly string[]).includes(chosen) ? chosen : "private";
  if (typeof organizationId !== "string" || !UUID.test(organizationId)) return failed("unavailable", 400);
  if (!(file instanceof File)) return failed("unsupported", 400);
  const problem = checkFile(file);
  if (problem) return failed(problem, problem === "tooLarge" ? 413 : 415);

  try {
    const base = `/organizations/${organizationId}/connections/`;
    const list = await backendFetch(base);
    let source: Connection | undefined;
    if (list.status === 403) {
      // Members may upload but not list connections: they ask for the
      // source itself, which an owner or admin created with the first file.
      const own = await backendFetch(`/organizations/${organizationId}/upload-source`);
      if (own.status === 404) return failed("noSource", 409);
      if (!own.ok) return failed(uploadErrorFromStatus(own.status), own.status);
      source = (await own.json()) as Connection;
    } else if (!list.ok) {
      return failed(uploadErrorFromStatus(list.status), list.status);
    } else {
      source = uploadSource((await list.json()) as Connection[]);
    }
    if (!source) {
      const created = await backendFetch(base, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: UPLOAD_PROVIDER, name: sourceName, settings: {} }),
      });
      if (!created.ok) return failed(uploadErrorFromStatus(created.status), created.status);
      source = (await created.json()) as Connection;
    }

    const body = new FormData();
    body.set("file", file, file.name);
    body.set("visibility", visibility);
    const response = await backendFetch(`${base}${source.id}/uploads/`, { method: "POST", body });
    if (!response.ok) return failed(uploadErrorFromStatus(response.status), response.status);
    return NextResponse.json(await response.json(), { status: 201 });
  } catch (error) {
    if (error instanceof SignedOutError) return failed("signedOut", 401);
    return failed("unavailable", 502);
  }
}
