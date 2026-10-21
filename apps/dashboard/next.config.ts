import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // untuk infra/docker/web.Dockerfile
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
