import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import { connectDatabase } from "@/app/(app)/definicoes/actions";
import { DatabasesPanel } from "@/components/settings/DatabasesPanel";
import type { DatabaseSource } from "@/lib/api-types";
import { auth0 } from "@/lib/auth0";

const ORG = "11111111-1111-4111-8111-111111111111";
const ID = "44444444-4444-4444-8444-444444444444";

const SALES: DatabaseSource = {
  id: ID,
  provider: "postgresql",
  name: "Vendas",
  status: "active",
  last_synced_at: "2026-11-22T10:00:00Z",
  last_error: null,
  disconnected_at: null,
  settings: { host: "db.example.com", port: 5432, database: "sales", sslmode: "require", schemas: ["sales"] },
  catalog: {
    schemas: ["sales"],
    truncated: false,
    tables: [
      {
        schema: "sales",
        name: "invoices",
        kind: "table",
        rows_estimate: 240,
        comment: "Faturas emitidas",
        columns: [
          { name: "id", type: "integer", nullable: false, comment: null },
          { name: "amount", type: "numeric", nullable: false, comment: null },
        ],
      },
    ],
  },
  catalogUpdatedAt: "2026-11-22T10:00:00Z",
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

function form(values: Record<string, string> = {}) {
  const data = new FormData();
  const all = {
    organizationId: ORG,
    name: "Vendas",
    host: "db.example.com",
    port: "5432",
    database: "sales",
    schemas: "sales, public",
    sslmode: "require",
    username: "reader",
    password: "secret-value",
    ...values,
  };
  for (const [key, value] of Object.entries(all)) data.set(key, value);
  return data;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("connectDatabase", () => {
  it("creates the connection, seals the login apart and asks for the tables", async () => {
    const fetchMock = backend(json({ id: ID }, 201), new Response(null, { status: 204 }), json({}, 202));
    expect(await connectDatabase({}, form())).toEqual({ done: "connected" });

    const [, create] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(create.body))).toEqual({
      provider: "postgresql",
      name: "Vendas",
      settings: { host: "db.example.com", port: 5432, database: "sales", sslmode: "require", schemas: ["sales", "public"] },
    });
    // The password goes only to the sealed store, never in the settings.
    expect(String(create.body)).not.toContain("secret-value");
    const [url, seal] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toContain(`/connections/${ID}/credentials`);
    expect(seal.method).toBe("PUT");
    expect(fetchMock.mock.calls[2]?.[0]).toContain(`/connections/${ID}/sync`);
  });

  it("sends nothing when a field is missing or the port is not a port", async () => {
    const fetchMock = backend();
    expect(await connectDatabase({}, form({ password: "" }))).toEqual({ error: "invalid" });
    expect(await connectDatabase({}, form({ port: "70000" }))).toEqual({ error: "invalid" });
    expect(await connectDatabase({}, form({ schemas: "sales; drop" }))).toEqual({ error: "invalid" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("takes the connection away again when its login cannot be stored", async () => {
    const fetchMock = backend(json({ id: ID }, 201), json({}, 503), json({}, 200));
    expect(await connectDatabase({}, form())).toEqual({ error: "unavailable" });
    expect(fetchMock.mock.calls[2]?.[0]).toContain(`/connections/${ID}/disconnect`);
  });

  it("says when the server refuses the details or the name is taken", async () => {
    backend(json({ detail: "sslmode disable is allowed only in development" }, 400));
    expect(await connectDatabase({}, form())).toEqual({ error: "refused" });
    backend(json({ detail: "taken" }, 409));
    expect(await connectDatabase({}, form())).toEqual({ error: "nameTaken" });
  });
});

describe("DatabasesPanel", () => {
  it("asks for a read-only login before connecting", async () => {
    render(<DatabasesPanel organizationId={ORG} databases={[]} connect={vi.fn(async () => ({}))} />);
    expect(screen.getByText("Ainda n\u00e3o ligaste nenhuma base de dados.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ligar base de dados" }));
    expect(screen.getByText("Usa um login que s\u00f3 pode ler")).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/)).toHaveAttribute("type", "password");
  });

  it("shows what was read, names only, and asks before disconnecting", async () => {
    const disconnect = vi.fn(async () => ({ done: "disconnected" as const }));
    render(<DatabasesPanel organizationId={ORG} databases={[SALES]} disconnect={disconnect} />);
    expect(screen.getByText("db.example.com:5432 / sales")).toBeInTheDocument();
    expect(screen.getByText(/^1 tabela lida em/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Ver tabelas" }));
    expect(screen.getByText("sales.invoices")).toBeInTheDocument();
    expect(screen.getByText("id, amount")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Desligar" }));
    expect(disconnect).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Sim, desligar" }));
    expect(disconnect).toHaveBeenCalledTimes(1);
  });

  it("keeps looking while the tables are being read", () => {
    vi.useFakeTimers();
    render(<DatabasesPanel organizationId={ORG} databases={[{ ...SALES, catalog: null, catalogUpdatedAt: null }]} />);
    expect(screen.getByText("A ler as tabelas\u2026")).toBeInTheDocument();
    vi.advanceTimersByTime(4000);
    expect(refresh).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
