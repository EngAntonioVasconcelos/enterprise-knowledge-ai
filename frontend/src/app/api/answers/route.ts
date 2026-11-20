import { NextResponse } from "next/server";

import { backendFetch, SignedOutError } from "@/lib/backend";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_QUESTION = 500;

// The browser asks this route; this route asks the backend with the
// person's token. Only this one backend call is exposed, with checked input.
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "invalid body" }, { status: 400 });
  }
  const { organizationId, question } = (body ?? {}) as Record<string, unknown>;
  if (typeof organizationId !== "string" || !UUID.test(organizationId)) {
    return NextResponse.json({ detail: "invalid organization" }, { status: 400 });
  }
  if (typeof question !== "string" || !question.trim() || question.length > MAX_QUESTION) {
    return NextResponse.json({ detail: "invalid question" }, { status: 400 });
  }

  try {
    const response = await backendFetch(`/organizations/${organizationId}/answers/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question.trim() }),
    });
    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    if (error instanceof SignedOutError) {
      return NextResponse.json({ detail: "signed out" }, { status: 401 });
    }
    return NextResponse.json({ detail: "backend unreachable" }, { status: 502 });
  }
}
