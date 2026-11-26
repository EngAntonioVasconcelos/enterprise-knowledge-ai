import { render, screen, within } from "@testing-library/react";
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
    // All of the caller's own files, read or not, can be replaced.
    expect(data?.ownFiles.map((upload) => upload.id)).toEqual(["u-new", "u-old"]);
  });

  it("reads the list without managing it when the connections are not allowed", async () => {
    backend(json([]), json({}, 403), json({}, 403));
    expect(await loadDocuments(ORG)).toEqual({
      documents: [],
      canManage: false,
      canUpload: false,
      colleagues: [],
      waiting: [],
      ownFiles: [],
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
    expect(screen.queryByRole("button", { name: "Adicionar ficheiros" })).not.toBeInTheDocument();
  });

  it("explains at once why a file cannot be sent", async () => {
    render(<DocumentsView organizationId={ORG} documents={[]} canManage waiting={[]} lastError={null} />);
    await userEvent.click(screen.getByRole("button", { name: "Adicionar ficheiros" }));
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
    await userEvent.click(screen.getByRole("button", { name: "Adicionar ficheiros" }));
    expect(screen.getByRole("radio", { name: /S\u00f3 eu/ })).toBeChecked();

    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "notas.txt", { type: "text/plain" }));
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).body).toBeInstanceOf(FormData);
    expect(((fetchMock.mock.calls[0]?.[1] as RequestInit).body as FormData).get("visibility")).toBe("private");

    await userEvent.click(screen.getByRole("radio", { name: /Toda a organiza\u00e7\u00e3o/ }));
    await userEvent.upload(input, new File(["y"], "manual.txt", { type: "text/plain" }));
    expect(((fetchMock.mock.calls[1]?.[1] as RequestInit).body as FormData).get("visibility")).toBe("organization");
  });

  it("is the whole organization by default for owners and admins", async () => {
    render(<DocumentsView organizationId={ORG} documents={[]} canManage waiting={[]} lastError={null} />);
    await userEvent.click(screen.getByRole("button", { name: "Adicionar ficheiros" }));
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
    await userEvent.click(screen.getByRole("button", { name: "Adicionar ficheiros" }));

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
    const table = within(screen.getByRole("table"));
    expect(table.getByText("Google Drive")).toBeInTheDocument();
    expect(table.getByText("Como na origem")).toBeInTheDocument();
    expect(screen.getByText("S\u00f3 tu")).toBeInTheDocument();
    expect(screen.getByText("Tu e pessoas escolhidas")).toBeInTheDocument();
    expect(table.getAllByText("Ficheiros enviados")).toHaveLength(2);
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

describe("finding a document", () => {
  const documents = [
    { id: "d1", connection_id: "c", title: "Manual de f\u00e9rias.pdf", mime_type: "application/pdf", status: "active", last_synced_at: null, updated_at: "2026-11-20T09:00:00Z" },
    { id: "d2", connection_id: "c", title: "Notas.txt", mime_type: "text/plain", status: "failed", last_synced_at: null, updated_at: "2026-11-20T09:00:00Z" },
    { id: "d3", connection_id: "c", title: "Plano.txt", mime_type: "text/plain", status: "active", last_synced_at: null, updated_at: "2026-11-20T09:00:00Z" },
  ];

  it("searches by name without minding accents, and by state", async () => {
    render(<DocumentsView organizationId={ORG} documents={documents} canManage={false} waiting={[]} lastError={null} />);
    expect(screen.getByText("3 documentos")).toBeInTheDocument();

    await userEvent.type(screen.getByRole("searchbox", { name: "Procurar pelo nome" }), "ferias");
    expect(screen.getByText("A mostrar 1 de 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manual de f\u00e9rias.pdf" })).toBeInTheDocument();

    await userEvent.clear(screen.getByRole("searchbox", { name: "Procurar pelo nome" }));
    await userEvent.click(screen.getByRole("radio", { name: /Com erro/ }));
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(screen.getByRole("row", { name: /Notas\.txt/ })).toBeInTheDocument();
  });

  it("offers to clear the filters when nothing matches", async () => {
    render(<DocumentsView organizationId={ORG} documents={documents} canManage={false} waiting={[]} lastError={null} />);
    await userEvent.type(screen.getByRole("searchbox", { name: "Procurar pelo nome" }), "contrato");
    expect(screen.getByText("Nenhum documento corresponde a estes filtros.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    expect(screen.getByText("3 documentos")).toBeInTheDocument();
  });
});

describe("a file whose name already exists", () => {
  const manual = { id: "d1", connection_id: SOURCE.id, title: "Manual.pdf", mime_type: "application/pdf", status: "active", last_synced_at: null, updated_at: "2026-11-20T09:00:00Z" };
  const mine = { id: "u1", connection_id: SOURCE.id, filename: "Manual.pdf", mime_type: "application/pdf", size_bytes: 3, created_at: "2026-11-20T08:00:00Z" };

  async function chooseFile(name: string) {
    await userEvent.click(screen.getByRole("button", { name: "Adicionar ficheiros" }));
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, new File(["%PDF"], name, { type: "application/pdf" }));
  }

  it("replaces your own file: the new one goes in, then the old one comes out", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ id: "u2" }, 201)).mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DocumentsView organizationId={ORG} documents={[manual]} ownFiles={[mine]} canManage waiting={[]} lastError={null} />);
    await chooseFile("manual.pdf");

    expect(screen.getByText("Este ficheiro j\u00e1 existe")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("radio", { name: "Substituir" })).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));

    expect(await screen.findByText("manual.pdf: substitu\u00eddo.")).toBeInTheDocument();
    const [url, removal] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("/api/uploads");
    expect(removal.method).toBe("DELETE");
    expect(JSON.parse(String(removal.body))).toEqual({ organizationId: ORG, connectionId: SOURCE.id, uploadId: "u1" });
  });

  it("cannot replace another person's file, and can send nothing", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<DocumentsView organizationId={ORG} documents={[manual]} canManage={false} canUpload waiting={[]} lastError={null} />);
    await chooseFile("Manual.pdf");

    expect(screen.getByRole("radio", { name: "Substituir" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Manter os dois" })).toBeChecked();
    expect(screen.getByText(/n\u00e3o foi enviado por ti/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "N\u00e3o enviar" }));
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
