// @vitest-environment node
// Route handlers read multipart bodies with Node's own Request.
vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));

import { POST } from "@/app/api/uploads/route";
import { auth0 } from "@/lib/auth0";

const ORG = "11111111-1111-4111-8111-111111111111";
const SOURCE = {
  id: "22222222-2222-4222-8222-222222222222",
  provider: "file_upload",
  name: "Ficheiros enviados",
  status: "active",
  last_synced_at: "2026-11-20T10:00:00Z",
  last_error: null,
  disconnected_at: null,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function backend(...responses: Response[]) {
  vi.mocked(auth0.getAccessToken).mockResolvedValue({ token: "t" } as never);
  const fetchMock = vi.fn();
  for (const response of responses) fetchMock.mockResolvedValueOnce(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function uploadRequest(name: string, content = "Ferias: 25 dias.", visibility = "organization") {
  const form = new FormData();
  form.set("organizationId", ORG);
  form.set("visibility", visibility);
  form.set("sourceName", "Ficheiros enviados");
  form.set("file", new File([content], name, { type: "text/plain" }));
  return new Request("http://localhost/api/uploads", { method: "POST", body: form });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("POST /api/uploads", () => {
  it("creates the upload source on the first upload, then sends the file", async () => {
    const fetchMock = backend(json([]), json(SOURCE, 201), json({ id: "u1" }, 201));
    const response = await POST(uploadRequest("manual.txt"));

    expect(response.status).toBe(201);
    const [, create] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(create.body).toBe(JSON.stringify({ provider: "file_upload", name: "Ficheiros enviados", settings: {} }));
    const [url, send] = fetchMock.mock.calls[2] as [string, RequestInit];
    expect(url).toContain(`/organizations/${ORG}/connections/${SOURCE.id}/uploads/`);
    expect((send.body as FormData).get("visibility")).toBe("organization");
  });

  it("reuses the source that exists", async () => {
    const fetchMock = backend(json([SOURCE]), json({ id: "u1" }, 201));
    expect((await POST(uploadRequest("manual.txt"))).status).toBe(201);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("refuses a file type the backend cannot read, before calling it", async () => {
    const fetchMock = backend();
    const response = await POST(uploadRequest("photo.png"));
    expect(response.status).toBe(415);
    expect(await response.json()).toEqual({ error: "unsupported" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says when the person may not add documents", async () => {
    backend(json({}, 403), json({}, 403));
    expect(await (await POST(uploadRequest("manual.txt"))).json()).toEqual({ error: "forbidden" });
  });

  it("sends a member's file to the source they may use, private when they say so", async () => {
    const fetchMock = backend(json({}, 403), json(SOURCE), json({ id: "u1" }, 201));
    expect((await POST(uploadRequest("notas.txt", "x", "private"))).status).toBe(201);
    expect(fetchMock.mock.calls[1]?.[0]).toContain(`/organizations/${ORG}/upload-source`);
    const [url, send] = fetchMock.mock.calls[2] as [string, RequestInit];
    expect(url).toContain(`/connections/${SOURCE.id}/uploads/`);
    expect((send.body as FormData).get("visibility")).toBe("private");
  });

  it("says plainly when nobody has opened the uploads yet", async () => {
    backend(json({}, 403), json({}, 404));
    const response = await POST(uploadRequest("notas.txt"));
    expect(response.status).toBe(409);
    expect(await response.json()).toEqual({ error: "noSource" });
  });

  it("keeps a file private when no choice arrives", async () => {
    const form = new FormData();
    form.set("organizationId", ORG);
    form.set("file", new File(["x"], "a.txt", { type: "text/plain" }));
    const fetchMock = backend(json([SOURCE]), json({ id: "u1" }, 201));
    await POST(new Request("http://localhost/api/uploads", { method: "POST", body: form }));
    expect(((fetchMock.mock.calls[1] as [string, RequestInit])[1].body as FormData).get("visibility")).toBe("private");
  });
});
