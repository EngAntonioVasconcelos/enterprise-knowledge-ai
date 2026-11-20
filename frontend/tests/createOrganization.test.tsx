import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));
const redirect = vi.fn();
vi.mock("next/navigation", () => ({ redirect: (to: string) => redirect(to) }));

import { createOrganization } from "@/app/(app)/assistente/actions";
import { CreateOrganization } from "@/components/onboarding/CreateOrganization";
import { auth0 } from "@/lib/auth0";
import { slugify } from "@/lib/slug";

function form(name: string) {
  const data = new FormData();
  data.set("name", name);
  return data;
}

function backend(...statuses: number[]) {
  vi.mocked(auth0.getAccessToken).mockResolvedValue({ token: "t" } as never);
  const fetchMock = vi.fn();
  for (const status of statuses) {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "org-1", name: "x", slug: "x", status: "active" }), { status }),
    );
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("slugify", () => {
  it("makes a technical name from the name", () => {
    expect(slugify("Atl\u00e2ntico Seguros, S.A.")).toBe("atlantico-seguros-s-a");
    expect(slugify("  \u00c9quipe   Fran\u00e7aise ")).toBe("equipe-francaise");
    expect(slugify("!!")).toBe("org");
  });
});

describe("createOrganization", () => {
  it("creates the organization and opens the assistant in it", async () => {
    const fetchMock = backend(201);
    await createOrganization({}, form("  Atl\u00e2ntico   Seguros "));
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.body).toBe(JSON.stringify({ name: "Atl\u00e2ntico Seguros", slug: "atlantico-seguros" }));
    expect(redirect).toHaveBeenCalledWith("/assistente?org=org-1");
  });

  it("adds a short ending when the technical name is taken", async () => {
    const fetchMock = backend(409, 201);
    await createOrganization({}, form("Atlantico"));
    const second = JSON.parse((fetchMock.mock.calls[1] as [string, RequestInit])[1].body as string);
    expect(second.slug).toMatch(/^atlantico-[0-9a-f]{6}$/);
    expect(redirect).toHaveBeenCalled();
  });

  it("refuses a name that is too short before calling the backend", async () => {
    const fetchMock = backend();
    expect(await createOrganization({}, form("A"))).toEqual({ error: "invalid", name: "A" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says when the session was refused", async () => {
    backend(401);
    expect(await createOrganization({}, form("Atlantico"))).toEqual({ error: "signedOut", name: "Atlantico" });
    expect(redirect).not.toHaveBeenCalled();
  });
});

describe("CreateOrganization", () => {
  it("sends the name and shows what went wrong", async () => {
    const action = vi.fn().mockResolvedValue({ error: "unavailable", name: "Atlantico" });
    render(<CreateOrganization action={action} />);

    await userEvent.type(screen.getByLabelText("Nome da organiza\u00e7\u00e3o"), "Atlantico");
    await userEvent.click(screen.getByRole("button", { name: "Criar organiza\u00e7\u00e3o" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("N\u00e3o foi poss\u00edvel criar a organiza\u00e7\u00e3o");
    expect((action.mock.calls[0]?.[1] as FormData).get("name")).toBe("Atlantico");
  });
});
