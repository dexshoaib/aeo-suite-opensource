import type { NextConfig } from "next";

// Same-origin proxy: the browser only ever talks to this Next.js origin.
// /api/* requests are forwarded server-side to BACKEND_ORIGIN, so session
// cookies stay first-party and the backend needs no CORS middleware.
// BACKEND_ORIGIN is read server-side only and is never exposed to the
// browser bundle; it defaults to the local Django dev server.
const backendOrigin = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
