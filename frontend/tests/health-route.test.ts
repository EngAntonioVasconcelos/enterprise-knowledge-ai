// @vitest-environment node
import { GET } from "@/app/health/route";
import { readFileSync } from "node:fs";

afterEach(() => vi.unstubAllGlobals());

describe("the health check for the uptime monitor", () => {
  it("is ok when the API and the database answer", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    const response = await GET();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ok" });
    expect(fetch.mock.calls[0]?.[0]).toMatch(/\/health\/ready$/);
  });

  it("is unavailable when the database is down or the API is silent", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 503 })));
    expect((await GET()).status).toBe(503);

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("timeout")));
    const response = await GET();
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ status: "unavailable" });
  });

  it("needs no session, while every other path still does", () => {
    // The matcher of src/proxy.ts, read as text: importing the proxy would
    // load the Auth0 client.
    const source = readFileSync("src/proxy.ts", "utf8");
    const matcher = /matcher: \["([^"]+)"\]/.exec(source)?.[1] ?? "";
    const pattern = new RegExp(`^${matcher}$`);
    expect(pattern.test("/health")).toBe(false);
    expect(pattern.test("/assistente")).toBe(true);
    expect(pattern.test("/healthy")).toBe(true);
  });
});
