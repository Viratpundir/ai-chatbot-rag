import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const configuredBackend = process.env.API_BACKEND_URL?.trim();
    if (process.env.VERCEL && !configuredBackend) {
      throw new Error("Set API_BACKEND_URL to the deployed FastAPI origin for this Vercel project.");
    }

    const backend = (configuredBackend || "http://127.0.0.1:8000").replace(/\/$/, "");

    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
