import { defineConfig, devices } from "@playwright/test";

// 桩模型后端（backend/tests/e2e_app.py）+ Vite dev，均避开本地开发端口
const API = process.env.MEDSTA_E2E_API ?? "http://127.0.0.1:8021";
const WEB = process.env.MEDSTA_E2E_WEB ?? "http://127.0.0.1:5174";
const PYTHON = process.env.MEDSTA_PYTHON ?? "python";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: WEB,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${PYTHON} tests/e2e_app.py --port ${new URL(API).port}`,
      cwd: "../backend",
      url: `${API}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: `npm run dev -- --port ${new URL(WEB).port} --strictPort`,
      url: WEB,
      env: { ...process.env, MEDSTA_API: API },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
