vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth0", () => ({ auth0: { getAccessToken: vi.fn() } }));

import { auth0 } from "@/lib/auth0";
import { POST } from "@/app/api/answers/route";

const ORG = "11111111-1111-4111-8111-111111111111";

function call(body: unknown) {
  return POST(
    new Request("http://localhost/api/answers", { method: "POST", body: JSON.stringify(body) }),
  );
}

// The backend address comes from EKA_API_URL, which the development compose
// sets to http://api:8000: pin it here so the test means the same everywhere.
beforeEach(() => vi.stubEnv("EKA_API_URL", "http://backend.test:8000"));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("POST /api/answers", () => {
  it("forwards the question to the backend with the person's token", async () => {
    vi.mocked(auth0.getAccessToken).mockResolvedValue({ token: "secret-token" } as never);
    const backend = vi.fn().mockResolvedValue(new Response(JSON.stringify({ answer: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", backend);

    const response = await call({ organizationId: ORG, question: "  Quantos dias?  ", language: "fr" });

    expect(response.status).toBe(200);
    const [url, init] = backend.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`http://backend.test:8000/api/v1/organizations/${ORG}/answers/`);
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer secret-token");
    expect(init.body).toBe(JSON.stringify({ question: "Quantos dias?", interface_language: "fr" }));
  });

  it("refuses bad input before calling the backend", async () => {
    const backend = vi.fn();
    vi.stubGlobal("fetch", backend);

    expect((await call({ organizationId: "../admin", question: "x" })).status).toBe(400);
    expect((await call({ organizationId: ORG, question: "" })).status).toBe(400);
    expect((await call({ organizationId: ORG, question: "x".repeat(501) })).status).toBe(400);
    expect(backend).not.toHaveBeenCalled();
  });

  it("says signed out when there is no token", async () => {
    vi.mocked(auth0.getAccessToken).mockRejectedValue(new Error("no session"));
    vi.stubGlobal("fetch", vi.fn());
    expect((await call({ organizationId: ORG, question: "x" })).status).toBe(401);
  });
});
