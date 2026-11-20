vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));

import { auth0 } from "@/lib/auth0";
import { loadOrganizations } from "@/lib/organizations";

function backendAnswers(status: number, body: unknown = {}) {
  vi.mocked(auth0.getAccessToken).mockResolvedValue({ token: "t" } as never);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

afterEach(() => vi.unstubAllGlobals());

describe("loadOrganizations", () => {
  it("keeps only the active organizations", async () => {
    backendAnswers(200, [
      { id: "a", name: "A", slug: "a", status: "active" },
      { id: "b", name: "B", slug: "b", status: "suspended" },
    ]);
    expect(await loadOrganizations()).toEqual({
      organizations: [{ id: "a", name: "A", slug: "a", status: "active" }],
    });
  });

  it("never turns a refused session into an empty list", async () => {
    backendAnswers(401);
    expect(await loadOrganizations()).toEqual({ problem: "signedOut" });
  });

  it("tells an unconfirmed e-mail apart", async () => {
    backendAnswers(403);
    expect(await loadOrganizations()).toEqual({ problem: "unverified" });
  });

  it("reports the service as unavailable on other errors", async () => {
    backendAnswers(503);
    expect(await loadOrganizations()).toEqual({ problem: "unavailable" });
  });

  it("asks to sign in again when there is no token", async () => {
    vi.mocked(auth0.getAccessToken).mockRejectedValue(new Error("no session"));
    expect(await loadOrganizations()).toEqual({ problem: "signedOut" });
  });
});
