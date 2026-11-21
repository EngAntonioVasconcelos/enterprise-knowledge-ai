import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
const nav = { org: null as string | null, path: "/assistente" };
vi.mock("next/navigation", () => ({
  usePathname: () => nav.path,
  useSearchParams: () => new URLSearchParams(nav.org ? `org=${nav.org}` : ""),
}));

import { changeRole, invitePerson, removePerson, revokeInvitation } from "@/app/(app)/pessoas/actions";
import { PeopleView, type PeopleActions } from "@/components/people/PeopleView";
import { AppNav } from "@/components/shell/AppNav";
import { initials } from "@/components/shell/Avatar";
import type { Member } from "@/lib/api-types";
import { auth0 } from "@/lib/auth0";
import { assignableRoles, canManage, managesPeople } from "@/lib/roles";

const ORG = "11111111-1111-4111-8111-111111111111";
const USER = "33333333-3333-4333-8333-333333333333";
const INVITATION = "44444444-4444-4444-8444-444444444444";

function json(body: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(body), { status });
}

function backend(...responses: Response[]) {
  vi.mocked(auth0.getAccessToken).mockResolvedValue({ token: "t" } as never);
  const fetchMock = vi.fn();
  for (const response of responses) fetchMock.mockResolvedValueOnce(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function form(values: Record<string, string>) {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

function member(id: string, email: string, name: string | null, role: Member["membership"]["role"]): Member {
  return {
    id,
    email,
    full_name: name,
    is_active: true,
    membership: { id: `m-${id}`, organization_id: ORG, user_id: id, role, is_active: true },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("roles", () => {
  it("lets only owners give owner or admin", () => {
    expect(assignableRoles("owner")).toEqual(["owner", "admin", "member", "viewer"]);
    expect(assignableRoles("admin")).toEqual(["member", "viewer"]);
    expect(canManage("admin", "admin")).toBe(false);
    expect(canManage("admin", "viewer")).toBe(true);
    expect(canManage("owner", "owner")).toBe(true);
    expect(managesPeople("member")).toBe(false);
    expect(managesPeople(undefined)).toBe(false);
  });

  it("makes initials from the name, or the e-mail", () => {
    expect(initials("Ana Maria Sousa")).toBe("AS");
    expect(initials("ana")).toBe("AN");
    expect(initials(null, "rui@empresa.pt")).toBe("RU");
  });
});

describe("people actions", () => {
  it("invites by e-mail and returns the development token", async () => {
    const fetchMock = backend(json({ id: INVITATION, email: "rui@empresa.pt", role: "member", token: "tok" }, 201));
    const state = await invitePerson({}, form({ organizationId: ORG, email: " Rui@Empresa.pt ", role: "member" }));
    expect(state).toEqual({ invited: { email: "rui@empresa.pt", token: "tok" } });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(`/api/v1/organizations/${ORG}/invitations/`);
    expect(init.body).toBe(JSON.stringify({ email: "rui@empresa.pt", role: "member" }));
  });

  it("checks the e-mail before calling the server", async () => {
    const fetchMock = backend();
    const state = await invitePerson({}, form({ organizationId: ORG, email: "rui", role: "member" }));
    expect(state.error).toBe("invalidEmail");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("explains a pending invitation and a refused role", async () => {
    backend(json({}, 409), json({}, 403));
    expect((await invitePerson({}, form({ organizationId: ORG, email: "a@b.pt", role: "member" }))).error).toBe("pending");
    expect((await invitePerson({}, form({ organizationId: ORG, email: "a@b.pt", role: "admin" }))).error).toBe("forbidden");
  });

  it("changes a role, and says when the last owner would go", async () => {
    const fetchMock = backend(json({}), json({}, 409));
    expect(await changeRole({}, form({ organizationId: ORG, userId: USER, role: "viewer" }))).toEqual({ done: true });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(`/users/${USER}/membership`);
    expect(init.method).toBe("PATCH");
    expect((await changeRole({}, form({ organizationId: ORG, userId: USER, role: "member" }))).error).toBe("lastOwner");
  });

  it("removes a member and cancels an invitation already gone", async () => {
    backend(json(null, 204), json({}, 404));
    expect(await removePerson({}, form({ organizationId: ORG, userId: USER }))).toEqual({ done: true });
    expect(await revokeInvitation({}, form({ organizationId: ORG, invitationId: INVITATION }))).toEqual({ done: true });
  });

  it("refuses ids that are not ids", async () => {
    const fetchMock = backend();
    expect((await removePerson({}, form({ organizationId: ORG, userId: "../x" }))).error).toBe("unavailable");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("PeopleView", () => {
  const members = [
    member(USER, "ana@empresa.pt", "Ana Sousa", "owner"),
    member("55555555-5555-4555-8555-555555555555", "rui@empresa.pt", null, "member"),
    member("66666666-6666-4666-8666-666666666666", "eva@empresa.pt", "Eva Lima", "admin"),
  ];
  const actions = (overrides: Partial<PeopleActions> = {}): PeopleActions => ({
    invite: vi.fn(async () => ({})),
    change: vi.fn(async () => ({ done: true })),
    remove: vi.fn(async () => ({ done: true })),
    revoke: vi.fn(async () => ({ done: true })),
    ...overrides,
  });

  it("puts you first and keeps your own access out of reach", () => {
    render(
      <PeopleView organizationId={ORG} actorRole="owner" selfEmail="ana@empresa.pt" members={members} invitations={[]} actions={actions()} />,
    );
    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Ana Sousa (tu)");
    expect(within(rows[0]!).queryByRole("button", { name: "Remover" })).toBeNull();
    expect(within(rows[0]!).queryByRole("combobox")).toBeNull();
    expect(screen.getByText("3 pessoas")).toBeInTheDocument();
  });

  it("lets an admin manage members, but not admins", () => {
    render(
      <PeopleView organizationId={ORG} actorRole="admin" selfEmail="x@empresa.pt" members={members} invitations={[]} actions={actions()} />,
    );
    const eva = screen.getByText("Eva Lima").closest("li")!;
    expect(within(eva).queryByRole("button", { name: "Remover" })).toBeNull();
    const rui = screen.getByText("rui@empresa.pt").closest("li")!;
    expect(within(rui).getByRole("button", { name: "Remover" })).toBeInTheDocument();
    // The invite menu offers only what an admin may give.
    const select = screen.getByRole("combobox", { name: "Fun\u00e7\u00e3o" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Membro", "Leitor"]);
  });

  it("asks before removing someone", async () => {
    const remove = vi.fn(async () => ({ done: true }));
    render(
      <PeopleView organizationId={ORG} actorRole="owner" selfEmail="ana@empresa.pt" members={members} invitations={[]} actions={actions({ remove })} />,
    );
    const rui = screen.getByText("rui@empresa.pt").closest("li")!;
    await userEvent.click(within(rui).getByRole("button", { name: "Remover" }));
    expect(within(rui).getByText("Remover rui@empresa.pt? Perde o acesso de imediato.")).toBeInTheDocument();
    expect(remove).not.toHaveBeenCalled();
    await userEvent.click(within(rui).getByRole("button", { name: "Remover" }));
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it("shows the link to pass on while e-mails are not sent", async () => {
    const invite = vi.fn(async () => ({ invited: { email: "rui@empresa.pt", token: "abc" } }));
    render(
      <PeopleView organizationId={ORG} actorRole="owner" selfEmail="ana@empresa.pt" members={members} invitations={[]} actions={actions({ invite })} />,
    );
    await userEvent.type(screen.getByPlaceholderText("nome@empresa.pt"), "rui@empresa.pt");
    await userEvent.click(screen.getByRole("button", { name: "Enviar convite" }));
    expect(await screen.findByText("Convite criado para rui@empresa.pt.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Liga\u00e7\u00e3o do convite" })).toHaveValue(
      `${window.location.origin}/invitations/accept#token=abc`,
    );
  });

  it("lists pending invitations with a way to cancel them", () => {
    render(
      <PeopleView
        organizationId={ORG}
        actorRole="owner"
        selfEmail="ana@empresa.pt"
        members={members}
        invitations={[
          {
            id: INVITATION,
            organization_id: ORG,
            email: "novo@empresa.pt",
            role: "viewer",
            status: "pending",
            expires_at: "2026-11-28T10:00:00Z",
            created_at: "2026-11-21T10:00:00Z",
          },
        ]}
        actions={actions()}
      />,
    );
    const row = screen.getByText("novo@empresa.pt").closest("li")!;
    expect(row).toHaveTextContent("Leitor, expira a");
    expect(within(row).getByRole("button", { name: "Cancelar convite" })).toBeInTheDocument();
  });
});

describe("AppNav", () => {
  it("shows People only where the person manages people", () => {
    nav.org = null;
    const { rerender } = render(<AppNav managed={[ORG]} fallback={ORG} />);
    expect(screen.getByRole("link", { name: "Pessoas" })).toHaveAttribute("href", "/pessoas");
    nav.org = "77777777-7777-4777-8777-777777777777";
    rerender(<AppNav managed={[ORG]} fallback={ORG} />);
    expect(screen.queryByRole("link", { name: "Pessoas" })).toBeNull();
  });
});
