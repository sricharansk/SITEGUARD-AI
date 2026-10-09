import { defineConfig, devices } from "@playwright/test";

// Browser E2E against a running web app and API (see frontend/README.md).
// E2E_WEB_URL: the Next.js app (default http://localhost:3000). It must reach the API through SITEGUARD_API_URL.
// PW_CHROMIUM_PATH: optional Chromium binary, for machines where browsers are preinstalled instead of downloaded
// with `npx playwright install`.
const executablePath = process.env.PW_CHROMIUM_PATH || undefined;

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: process.env.E2E_WEB_URL || "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], launchOptions: executablePath ? { executablePath } : {} },
    },
  ],
});
