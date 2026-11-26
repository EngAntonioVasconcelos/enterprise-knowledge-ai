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
const RUI = "33333333-3333-4333-8333-333333333333";
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
      json([]),
    );
    const data = await loadDocuments(ORG);
    expect(data?.canManage).toBe(true);
    expect(data?.waiting.map((upload) => upload.id)).toEqual(["u-new"]);
  });

  it("reads the list without managing it when the connections are not allowed", async () => {
    backend(json([]), json({}, 403), json({}, 403));
    expect(await loadDocuments(ORG)).toEqual({
      documents: [],
      canManage: false,
      canUpload: false,
      colleagues: [],
      waiting: [],
      lastError: null,
      drive: null,
    });
  });

  it("lets a member send files and see their own waiting ones", async () => {
    const fetchMock = backend(
      json([]),
      json({}, 403),
      json(SOURCE),
      json([{ id: "u-new", connection_id: SOURCE.id, filename: "Mine.pdf", mime_type: "application/pdf", size_bytes: 3, created_at: "2026-11-20T11:00:00Z" }]),
      json([{ user_id: RUI, full_name: "Rui Costa", role: "member" }]),
    );
    const data = await loadDocuments(ORG);
    expect(data?.colleagues.map((colleague) => colleague.full_name)).toEqual(["Rui Costa"]);
    expect(fetchMock.mock.calls[2]?.[0]).toContain(`/organizations/${ORG}/upload-source`);
    expect(data).toMatchObject({ canManage: false, canUpload: true });
    expect(data?.waiting.map((upload) => upload.id)).toEqual(["u-new"]);
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

  it("tells a viewer that they read documents but do not add them", () => {
    render(<DocumentsView organizationId={ORG} documents={[]} canManage={false} waiting={[]} lastError={null} />);
    expect(screen.getByText(/Com a fun\u00e7\u00e3o de leitor/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /escolhe no computador/ })).not.toBeInTheDocument();
  });

  it("explains at once why a file cannot be sent", async () => {
    render(<DocumentsView organizationId={ORG} documents={[]} canManage waiting={[]} lastError={null} />);
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "foto.png", { type: "image/png" }), { applyAccept: false });
    expect(await screen.findByRole("alert")).toHaveTextContent("foto.png: n\u00e3o \u00e9 PDF, Word (.docx) nem texto.");
  });
});

describe("who can see a sent file", () => {
  it("is only the member, unless they choose the whole organization", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ id: "u1" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<DocumentsView organizationId={ORG} documents={[]} canManage={false} canUpload waiting={[]} lastError={null} />);
    expect(screen.getByRole("radio", { name: /S\u00f3 eu/ })).toBeChecked();

    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "notas.txt", { type: "text/plain" }));
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).body).toBeInstanceOf(FormData);
    expect(((fetchMock.mock.calls[0]?.[1] as RequestInit).body as FormData).get("visibility")).toBe("private");

    await userEvent.click(screen.getByRole("radio", { name: /Toda a organiza\u00e7\u00e3o/ }));
    await userEvent.upload(input, new File(["y"], "manual.txt", { type: "text/plain" }));
    expect(((fetchMock.mock.calls[1]?.[1] as RequestInit).body as FormData).get("visibility")).toBe("organization");
  });

  it("is the whole organization by default for owners and admins", () => {
    render(<DocumentsView organizationId={ORG} documents={[]} canManage waiting={[]} lastError={null} />);
    expect(screen.getByRole("radio", { name: /Toda a organiza\u00e7\u00e3o/ })).toBeChecked();
  });
});

describe("sharing with chosen people", () => {
  const colleagues = [
    { user_id: RUI, full_name: "Rui Costa", role: "member" as const },
    { user_id: "44444444-4444-4444-8444-444444444444", full_name: "Ana Lopes", role: "admin" as const },
  ];

  it("sends only after someone is chosen, and sends who", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ id: "u1" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<DocumentsView organizationId={ORG} documents={[]} canManage={false} canUpload colleagues={colleagues} waiting={[]} lastError={null} />);

    await userEvent.click(screen.getByRole("radio", { name: /Pessoas escolhidas/ }));
    expect(screen.getByText("Escolhe pelo menos uma pessoa antes de enviar.")).toBeInTheDocument();
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "plano.txt", { type: "text/plain" }));
    expect(fetchMock).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("checkbox", { name: /Rui Costa/ }));
    expect(screen.getByText("1 pessoa escolhida")).toBeInTheDocument();
    await userEvent.upload(input, new File(["x"], "plano.txt", { type: "text/plain" }));
    const body = (fetchMock.mock.calls[0]?.[1] as RequestInit).body as FormData;
    expect(body.get("visibility")).toBe("people");
    expect(body.getAll("readers")).toEqual([RUI]);
  });
});

describe("where a document comes from and who sees it", () => {
  it("shows the source and the kind of sharing, never who", () => {
    render(
      <DocumentsView
        organizationId={ORG}
        canManage={false}
        waiting={[{ id: "w1", connection_id: "c", filename: "Plano.txt", mime_type: "text/plain", size_bytes: 1, visibility: "people", created_at: "2026-11-26T10:00:00Z" }]}
        lastError={null}
        documents={[
          { id: "d1", connection_id: "c", title: "Manual.pdf", mime_type: "application/pdf", status: "active", last_synced_at: null, updated_at: "2026-11-20T09:00:00Z", source: { provider: "google_drive", name: "Drive" }, audience: "source" },
          { id: "d2", connection_id: "c", title: "Notas.txt", mime_type: "text/plain", status: "active", last_synced_at: null, updated_at: "2026-11-20T09:00:00Z", source: { provider: "file_upload", name: "Ficheiros" }, audience: "only_you" },
        ]}
      />,
    );
    expect(screen.getByText("Google Drive")).toBeInTheDocument();
    expect(screen.getByText("Como na origem")).toBeInTheDocument();
    expect(screen.getByText("S\u00f3 tu")).toBeInTheDocument();
    expect(screen.getByText("Tu e pessoas escolhidas")).toBeInTheDocument();
    expect(screen.getAllByText("Ficheiros enviados")).toHaveLength(2);
  });
});

describe("each document opens its own page", () => {
  it("links documents, not files still waiting", () => {
    render(
      <DocumentsView
        organizationId={ORG}
        canManage
        waiting={[{ id: "w1", connection_id: "c", filename: "A caminho.txt", mime_type: "text/plain", size_bytes: 1, created_at: "2026-11-26T10:00:00Z" }]}
        lastError={null}
        documents={[{ id: "d9", connection_id: "c", title: "Manual.pdf", mime_type: "application/pdf", status: "active", last_synced_at: null, updated_at: "2026-11-20T09:00:00Z" }]}
      />,
    );
    expect(screen.getByRole("link", { name: "Manual.pdf" })).toHaveAttribute("href", `/documentos/d9?org=${ORG}`);
    expect(screen.queryByRole("link", { name: "A caminho.txt" })).not.toBeInTheDocument();
  });
});
