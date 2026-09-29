import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const configuredBackend = process.env.API_BACKEND_URL?.trim();
    const isVercel = Boolean(process.env.VERCEL);
    if (isVercel && !configuredBackend) {
      throw new Error("Set API_BACKEND_URL to the deployed FastAPI HTTPS origin for this Vercel project.");
    }

    const backend = (configuredBackend || "http://127.0.0.1:8000").replace(/\/$/, "");
    if (isVercel) {
      let backendUrl: URL;
      try {
        backendUrl = new URL(backend);
      } catch {
        throw new Error("API_BACKEND_URL must be a valid HTTPS origin, for example https://api.example.com.");
      }
      const hostname = backendUrl.hostname.toLowerCase();
      if (
        backendUrl.protocol !== "https:" ||
        backendUrl.username ||
        backendUrl.password ||
        hostname === "localhost" ||
        hostname.endsWith(".localhost") ||
        hostname === "::1" ||
        hostname === "0.0.0.0" ||
        /^127\./.test(hostname)
      ) {
        throw new Error("On Vercel, API_BACKEND_URL must be a public HTTPS FastAPI origin, not localhost or an HTTP URL.");
      }
    }

    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
