import type { NextConfig } from "next";

// The FastAPI backend. Locally uvicorn on :8000; in production the Railway URL.
// Every /api and /pub request is proxied server-side, so the browser talks to one
// origin (cookies, no CORS) and the API URL never reaches the client.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      { source: "/pub/:path*", destination: `${API_URL}/pub/:path*` },
    ];
  },
};

export default nextConfig;
