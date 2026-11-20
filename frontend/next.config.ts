import type { NextConfig } from "next";

// Security headers for every page. The app talks only to itself (the
// backend is reached server-side), so the browser needs no other origin.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // Do not write AGENTS.md into the project at every start.
  agentRules: false,
  // The development badge sits bottom right, clear of the rail's name,
  // language and sign-out (it never shows in production).
  devIndicators: { position: "bottom-right" },
  experimental: {
    // Uploads pass through the proxy: allow the backend's 20 MB per file.
    proxyClientMaxBodySize: "21mb",
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
