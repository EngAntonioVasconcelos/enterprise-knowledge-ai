import { NextResponse, type NextRequest } from "next/server";

import { auth0 } from "@/lib/auth0";

// Every request passes here: Auth0 handles /auth/* (sign in, callback, sign
// out) and keeps the session fresh; pages of the app need a session.
export async function proxy(request: NextRequest) {
  const response = await auth0.middleware(request);
  const { pathname } = request.nextUrl;
  if (pathname.startsWith("/auth") || pathname === "/") return response;

  const session = await auth0.getSession(request);
  if (!session) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ detail: "signed out" }, { status: 401 });
    }
    return NextResponse.redirect(new URL("/", request.url));
  }
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)"],
};
