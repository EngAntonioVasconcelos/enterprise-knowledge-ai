import { NextResponse } from "next/server";
import type { OnCallbackHook } from "@auth0/nextjs-auth0/types";

// Why a sign-in came back without a session. "invite": the Auth0 Action
// "Only invited people" refused the account (access_denied); "failed":
// anything else (an expired attempt, a cancelled screen).
export type SignInProblem = "invite" | "failed";

export function signInProblem(error: unknown): SignInProblem {
  const cause = (error as { cause?: { code?: unknown } } | null)?.cause;
  return cause?.code === "access_denied" ? "invite" : "failed";
}

// The SDK's own answer to a failed callback is a bare text page. This sends
// the person back to the entry page, which says what happened and what to
// do, in their language. Success keeps the SDK's behaviour.
export const onCallback: OnCallbackHook = async (error, ctx) => {
  const base = ctx.appBaseUrl ?? process.env.APP_BASE_URL ?? "http://localhost:3000";
  if (error) {
    return NextResponse.redirect(new URL(`/?entrada=${signInProblem(error)}`, base));
  }
  return NextResponse.redirect(new URL(ctx.returnTo || "/", base));
};
