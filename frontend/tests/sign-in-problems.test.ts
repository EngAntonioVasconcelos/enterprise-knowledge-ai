// @vitest-environment node
import { onCallback, signInProblem } from "@/lib/auth-callback";

const ctx = { appBaseUrl: "https://demo.example" };

describe("a sign-in that comes back without a session", () => {
  it("tells a refused account apart from any other failure", () => {
    expect(signInProblem({ cause: { code: "access_denied" } })).toBe("invite");
    expect(signInProblem({ cause: { code: "login_required" } })).toBe("failed");
    expect(signInProblem(new Error("state"))).toBe("failed");
    expect(signInProblem(null)).toBe("failed");
  });

  it("goes back to the entry page instead of a bare error", async () => {
    const refused = await onCallback({ cause: { code: "access_denied" } } as never, ctx, null);
    expect(refused.status).toBe(307);
    expect(refused.headers.get("location")).toBe("https://demo.example/?entrada=invite");

    const failed = await onCallback(new Error("expired") as never, ctx, null);
    expect(failed.headers.get("location")).toBe("https://demo.example/?entrada=failed");
  });

  it("keeps the usual redirect after a successful sign-in", async () => {
    const ok = await onCallback(null, { ...ctx, returnTo: "/assistente" }, {} as never);
    expect(ok.headers.get("location")).toBe("https://demo.example/assistente");
  });
});
