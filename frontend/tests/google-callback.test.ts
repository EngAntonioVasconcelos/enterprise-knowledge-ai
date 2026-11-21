// @vitest-environment node
vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));

import { GET, stateTarget } from "@/app/connections/google/callback/route";
import { auth0 } from "@/lib/auth0";

const ORG = "11111111-1111-4111-8111-111111111111";
const DRIVE = "33333333-3333-4333-8333-333333333333";
const STATE = `${Buffer.from(JSON.stringify({ o: ORG, c: DRIVE, u: "x", n: "n", e: 1 })).toString("base64url")}.signature`;

function backend(...statuses: number[]) {
  vi.mocked(auth0.getAccessToken).mockResolvedValue({ token: "t" } as never);
  const fetchMock = vi.fn();
  for (const status of statuses) fetchMock.mockResolvedValueOnce(new Response("{}", { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function callback(query: string) {
  return GET(new Request(`http://localhost:3000/connections/google/callback?${query}`));
}

afterEach(() => vi.unstubAllGlobals());

describe("the Google callback", () => {
  it("reads where the signed state points, and nothing else", () => {
    expect(stateTarget(STATE)).toEqual({ organizationId: ORG, connectionId: DRIVE });
    expect(stateTarget("not-a-state")).toBeNull();
    const evil = `${Buffer.from(JSON.stringify({ o: "../x", c: DRIVE })).toString("base64url")}.s`;
    expect(stateTarget(evil)).toBeNull();
  });

  it("sends the code to the backend, queues the first reading and goes back", async () => {
    const fetchMock = backend(200, 202);
    const response = await callback(`code=abc&state=${STATE}`);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/organizations/${ORG}/connections/${DRIVE}/google/callback`);
    expect(init.body).toBe(JSON.stringify({ code: "abc", state: STATE }));
    expect(fetchMock.mock.calls[1]?.[0]).toContain(`/connections/${DRIVE}/sync`);
    expect(response.headers.get("location")).toBe(`http://localhost:3000/documentos?org=${ORG}&google=connected`);
  });

  it("says when the person cancelled at Google", async () => {
    const fetchMock = backend();
    const response = await callback(`error=access_denied&state=${STATE}`);
    expect(response.headers.get("location")).toContain("google=denied");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says when the authorization expired or was used", async () => {
    backend(400);
    expect((await callback(`code=abc&state=${STATE}`)).headers.get("location")).toContain("google=expired");
  });

  it("refuses a callback without a readable state", async () => {
    const fetchMock = backend();
    expect((await callback("code=abc&state=bad")).headers.get("location")).toBe(
      "http://localhost:3000/documentos?google=failed",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
