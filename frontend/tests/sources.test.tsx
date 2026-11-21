import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));
const refresh = vi.fn();
const redirect = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }), redirect: (to: string) => redirect(to) }));

import { connectGoogleDrive } from "@/app/(app)/documentos/actions";
import { SourcesPanel } from "@/components/documents/SourcesPanel";
import { auth0 } from "@/lib/auth0";

const ORG = "11111111-1111-4111-8111-111111111111";
const DRIVE = {
  id: "33333333-3333-4333-8333-333333333333",
  provider: "google_drive",
  name: "Google Drive",
  status: "active",
  last_synced_at: "2026-11-21T10:00:00Z",
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

function form() {
  const data = new FormData();
  data.set("organizationId", ORG);
  return data;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("connectGoogleDrive", () => {
  it("creates the Drive source the first time and opens Google", async () => {
    const fetchMock = backend(
      json([]),
      json(DRIVE, 201),
      json({ authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?x=1" }),
    );
    await connectGoogleDrive({}, form());
    const [, create] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(create.body).toBe(JSON.stringify({ provider: "google_drive", name: "Google Drive", settings: {} }));
    expect(fetchMock.mock.calls[2]?.[0]).toContain(`/connections/${DRIVE.id}/google/authorize`);
    expect(redirect).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/v2/auth?x=1");
  });

  it("follows only a Google address", async () => {
    backend(json([DRIVE]), json({ authorization_url: "https://evil.example/" }));
    expect(await connectGoogleDrive({}, form())).toEqual({ error: "unavailable" });
    expect(redirect).not.toHaveBeenCalled();
  });

  it("says when the server has no Google configuration", async () => {
    backend(json([DRIVE]), json({}, 503));
    expect(await connectGoogleDrive({}, form())).toEqual({ error: "notConfigured" });
  });
});

describe("SourcesPanel", () => {
  it("offers to connect Google Drive", () => {
    render(<SourcesPanel organizationId={ORG} drive={null} />);
    expect(screen.getByRole("button", { name: "Ligar Google Drive" })).toBeInTheDocument();
  });

  it("shows when it last synced and syncs on request", async () => {
    const sync = vi.fn().mockResolvedValue({ done: true });
    render(<SourcesPanel organizationId={ORG} drive={DRIVE} sync={sync} />);
    expect(screen.getByText(/Sincronizado a/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Sincronizar agora" }));
    expect(await screen.findByText(/Pedido enviado/)).toBeInTheDocument();
    expect((sync.mock.calls[0]?.[1] as FormData).get("connectionId")).toBe(DRIVE.id);
    expect(refresh).toHaveBeenCalled();
  });

  it("asks to authorize again when Google refused", () => {
    render(<SourcesPanel organizationId={ORG} drive={{ ...DRIVE, status: "error" }} />);
    expect(screen.getByText(/deixou de dar acesso/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Autorizar de novo" })).toBeInTheDocument();
  });
});
