/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// In development the API runs separately (`uv run radar api`); requests and the live
// WebSocket are proxied to it so the browser only ever talks to one origin.
// Set RADAR_API_URL in frontend/.env.local to point at a different API.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "RADAR_");
  const api = env.RADAR_API_URL ?? "http://127.0.0.1:8000";
  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        "/api": { target: api, changeOrigin: true, ws: true },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test-setup.ts"],
      css: false,
    },
  };
});
