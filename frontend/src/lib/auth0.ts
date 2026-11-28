import "server-only";

import { Auth0Client } from "@auth0/nextjs-auth0/server";

import { onCallback } from "@/lib/auth-callback";

// The session lives in an encrypted, http-only cookie on this server. The
// browser never sees the access token: requests to the backend are made by
// the Next.js server on the person's behalf (backend-for-frontend).
export const auth0 = new Auth0Client({
  authorizationParameters: {
    audience: process.env.AUTH0_AUDIENCE,
    scope: "openid profile email offline_access",
  },
  signInReturnToPath: "/assistente",
  onCallback,
});
