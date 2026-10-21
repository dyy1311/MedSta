import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev 默认 8000；E2E/并行开发可用 MEDSTA_API 指向桩后端（如 http://127.0.0.1:8021）
const API_TARGET = process.env.MEDSTA_API ?? "http://localhost:8000";
const WS_TARGET = API_TARGET.replace(/^http/, "ws");

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    allowedHosts: true,
    port: 5173,
    proxy: {
      "/sessions": API_TARGET,
      "/capabilities": API_TARGET,
      "/export": API_TARGET,
      "/data": API_TARGET,
      "/ws": {
        target: WS_TARGET,
        ws: true,
      },
    },
  },
});
