import { NextResponse } from "next/server";

// For the uptime monitor: 200 when the site, the API and the database all
// answer, 503 otherwise. Open without a session (src/proxy.ts leaves it out)
// and it says nothing about the inside: no versions, names or errors.
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };

export async function GET() {
  const base = process.env.EKA_API_URL ?? "http://localhost:8000";
  try {
    const ready = await fetch(`${base}/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (ready.ok) return NextResponse.json({ status: "ok" }, { headers: NO_STORE });
  } catch {
    // The API did not answer in time: same answer as "not ready".
  }
  return NextResponse.json({ status: "unavailable" }, { status: 503, headers: NO_STORE });
}
