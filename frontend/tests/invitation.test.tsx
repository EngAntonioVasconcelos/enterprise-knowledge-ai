import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { acceptInvitation } from "@/app/invitations/accept/actions";
import { AcceptInvitation, TOKEN_KEY } from "@/components/invitations/AcceptInvitation";
import { auth0 } from "@/lib/auth0";

const ORG = "11111111-1111-4111-8111-111111111111";
const TOKEN = "t".repeat(43);

function backend(status: number, body: unknown) {
  vi.mocked(auth0.getAccessToken).mockResolvedValue({ token: "t" } as never);
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function form(token: string) {
  const data = new FormData();
  data.set("token", token);
  return data;
}

beforeEach(() => {
  sessionStorage.clear();
  window.history.replaceState(null, "", "/invitations/accept");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("acceptInvitation", () => {
  it("joins the organization", async () => {
    const fetchMock = backend(200, { organization_id: ORG });
    expect(await acceptInvitation({}, form(TOKEN))).toEqual({ organizationId: ORG });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch("/api/v1/invitations/accept");
    expect(init.body).toBe(JSON.stringify({ token: TOKEN }));
  });

  it("tells another e-mail apart from an unconfirmed one", async () => {
    backend(403, { detail: "This invitation was sent to another email address." });
    expect((await acceptInvitation({}, form(TOKEN))).error).toBe("otherEmail");
    backend(403, { detail: "Email address is not verified." });
    expect((await acceptInvitation({}, form(TOKEN))).error).toBe("unverified");
  });

  it("explains used, expired and repeated invitations", async () => {
    backend(404, {});
    expect((await acceptInvitation({}, form(TOKEN))).error).toBe("invalid");
    backend(409, {});
    expect((await acceptInvitation({}, form(TOKEN))).error).toBe("alreadyMember");
    expect((await acceptInvitation({}, form("short"))).error).toBe("invalid");
  });
});

describe("AcceptInvitation", () => {
  it("keeps the token, takes it out of the address and asks to sign in", async () => {
    window.history.replaceState(null, "", `/invitations/accept#token=${TOKEN}`);
    render(<AcceptInvitation email={null} />);
    const signIn = await screen.findByRole("link", { name: "Entrar para aceitar" });
    expect(signIn).toHaveAttribute("href", "/auth/login?returnTo=%2Finvitations%2Faccept");
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe(TOKEN);
    expect(window.location.hash).toBe("");
  });

  it("accepts after signing in and opens the organization", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    const action = vi.fn(async () => ({ organizationId: ORG }));
    render(<AcceptInvitation email="rui@empresa.pt" action={action} />);
    expect(await screen.findByText("Vais aceitar como rui@empresa.pt.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Aceitar convite" }));
    // The page opens after the action answers, which can come a moment after the click.
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/assistente?org=${ORG}`));
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it("says when the link has no invitation", async () => {
    render(<AcceptInvitation email="rui@empresa.pt" />);
    expect(await screen.findByText("Falta o convite nesta liga\u00e7\u00e3o")).toBeInTheDocument();
  });

  it("offers another account when the invitation is for another e-mail", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    const action = vi.fn(async () => ({ error: "otherEmail" as const }));
    render(<AcceptInvitation email="rui@empresa.pt" action={action} />);
    await userEvent.click(await screen.findByRole("button", { name: "Aceitar convite" }));
    expect(await screen.findByRole("link", { name: "Sair e entrar com outra conta" })).toHaveAttribute("href", "/auth/logout");
  });
});
