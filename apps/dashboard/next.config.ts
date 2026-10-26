import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // untuk infra/docker/web.Dockerfile
  cacheComponents: true,
  partialPrefetching: true,
  // Workspace dirender di browser setelah sesi dicek (client auth gate), jadi
  // validasi instant otomatis per halaman hanya menghasilkan peringatan dev.
  // Validasi tetap berlaku untuk segmen yang menyatakan `instant` eksplisit.
  experimental: {
    instantInsights: { validationLevel: "manual-warning" },
  },
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
