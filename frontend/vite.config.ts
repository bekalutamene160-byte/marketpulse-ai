/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    // The dev proxy makes the browser see ONE origin (localhost:5173), so the
    // HttpOnly session cookie (SameSite=Lax) works without CORS or HTTPS games —
    // the same shape as the production reverse proxy (blueprint 19.2).
    proxy: {
      "/api": {
        target: process.env["VITE_API_BASE_URL"] ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
