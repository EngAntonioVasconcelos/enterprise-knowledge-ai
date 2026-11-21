import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import { DocumentsView } from "@/components/documents/DocumentsView";
import { auth0 } from "@/lib/auth0";
import { loadDocuments } from "@/lib/documents";

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

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("loadDocuments", () => {
  it("lists files sent after the last reading as waiting", async () => {
    backend(
      json([{ id: "d1", connection_id: SOURCE.id, title: "Old.pdf", mime_type: "application/pdf", status: "active", last_synced_at: null, updated_at: "2026-11-20T09:00:00Z" }]),
      json([SOURCE]),
      json([
        { id: "u-new", connection_id: SOURCE.id, filename: "New.pdf", mime_type: "application/pdf", size_bytes: 3, created_at: "2026-11-20T11:00:00Z" },
        { id: "u-old", connection_id: SOURCE.id, filename: "Old.pdf", mime_type: "application/pdf", size_bytes: 3, created_at: "2026-11-20T09:00:00Z" },
      ]),
    );
    const data = await loadDocuments(ORG);
    expect(data?.canManage).toBe(true);
    expect(data?.waiting.map((upload) => upload.id)).toEqual(["u-new"]);
  });

  it("reads the list without managing it when the connections are not allowed", async () => {
    backend(json([]), json({}, 403));
    expect(await loadDocuments(ORG)).toEqual({
      documents: [],
      canManage: false,
      waiting: [],
      lastError: null,
      drive: null,
    });
  });
});

describe("DocumentsView", () => {
  const documents = [
    { id: "d1", connection_id: "c", title: "Manual.pdf", mime_type: "application/pdf", status: "active", last_synced_at: null, updated_at: "2026-11-20T09:00:00Z" },
    { id: "d2", connection_id: "c", title: "Notas.txt", mime_type: "text/plain", status: "failed", last_synced_at: null, updated_at: "2026-11-20T09:00:00Z" },
  ];

  it("shows each document with its state in plain words", () => {
    render(<DocumentsView organizationId={ORG} documents={documents} canManage waiting={[]} lastError={null} />);
    expect(screen.getByRole("row", { name: /Manual\.pdf.*Pronto/ })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Notas\.txt.*N\u00e3o foi poss\u00edvel ler/ })).toBeInTheDocument();
  });

  it("tells a reader that only managers add documents", () => {
    render(<DocumentsView organizationId={ORG} documents={[]} canManage={false} waiting={[]} lastError={null} />);
    expect(screen.getByText(/S\u00f3 propriet\u00e1rios e administradores/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /escolhe no computador/ })).not.toBeInTheDocument();
  });

  it("explains at once why a file cannot be sent", async () => {
    render(<DocumentsView organizationId={ORG} documents={[]} canManage waiting={[]} lastError={null} />);
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "foto.png", { type: "image/png" }), { applyAccept: false });
    expect(await screen.findByRole("alert")).toHaveTextContent("foto.png: n\u00e3o \u00e9 PDF, Word (.docx) nem texto.");
  });
});
