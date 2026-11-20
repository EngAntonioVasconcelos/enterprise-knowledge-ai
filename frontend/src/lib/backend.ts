import "server-only";

import { auth0 } from "@/lib/auth0";

// Calls the backend API as the signed-in person. Server-side only: the
// access token is added here and never reaches the browser.

export class SignedOutError extends Error {}

function apiUrl(path: string): string {
  const base = process.env.EKA_API_URL ?? "http://localhost:8000";
  return `${base.replace(/\/$/, "")}/api/v1${path}`;
}

export async function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  let token: string;
  try {
    ({ token } = await auth0.getAccessToken());
  } catch {
    throw new SignedOutError("no access token");
  }
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("Accept", "application/json");
  return fetch(apiUrl(path), { ...init, headers, cache: "no-store" });
}
