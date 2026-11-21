import { NextResponse } from "next/server";

import { backendFetch } from "@/lib/backend";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Which organization and source the signed state names. Read only to know
 * where to send the code; the backend checks the signature, the person and
 * the expiry before it accepts anything.
 */
export function stateTarget(state: string): { organizationId: string; connectionId: string } | null {
  try {
    const [body] = state.split(".");
    const data = JSON.parse(Buffer.from(body ?? "", "base64url").toString("utf8")) as Record<string, unknown>;
    const organizationId = String(data.o ?? "");
    const connectionId = String(data.c ?? "");
    return UUID.test(organizationId) && UUID.test(connectionId) ? { organizationId, connectionId } : null;
  } catch {
    return null;
  }
}

// Google sends the browser here after the consent page. The code is
// exchanged by the backend (the token is sealed there and never comes
// back), the first reading is queued, and the person returns to the
// Documents screen with the outcome.
export async function GET(request: Request) {
  const url = new URL(request.url);
  const params = url.searchParams;
  const target = stateTarget(params.get("state") ?? "");
  const back = (outcome: string, organizationId?: string) => {
    const next = new URL("/documentos", url);
    if (organizationId) next.searchParams.set("org", organizationId);
    next.searchParams.set("google", outcome);
    return NextResponse.redirect(next);
  };

  if (!target) return back("failed");
  if (params.get("error")) return back("denied", target.organizationId);
  const code = params.get("code");
  if (!code) return back("failed", target.organizationId);

  const base = `/organizations/${target.organizationId}/connections/${target.connectionId}`;
  try {
    const done = await backendFetch(`${base}/google/callback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, state: params.get("state") }),
    });
    if (!done.ok) return back(done.status === 400 ? "expired" : "failed", target.organizationId);
    await backendFetch(`${base}/sync`, { method: "POST" });
  } catch {
    return back("failed", target.organizationId);
  }
  return back("connected", target.organizationId);
}
