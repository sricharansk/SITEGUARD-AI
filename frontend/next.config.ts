import type { NextConfig } from "next";

// Static export served by the FastAPI app at /app (backend/app/main.py). No Node server in production.
const nextConfig: NextConfig = {
  output: "export",
  basePath: "/app",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
