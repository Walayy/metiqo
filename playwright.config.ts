import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: true,
  preserveOutput: "always",
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  webServer: {
    command: "pnpm --filter @metiquo/web build && pnpm --filter @metiquo/web start",
    reuseExistingServer: process.env.CI !== "true",
    timeout: 120_000,
    url: "http://127.0.0.1:3000/health",
  },
  use: {
    baseURL: "http://127.0.0.1:3000",
    browserName: "chromium",
    locale: "fr-FR",
    screenshot: "only-on-failure",
    timezoneId: "Europe/Paris",
    trace: "retain-on-failure",
    viewport: { height: 960, width: 1440 },
  },
});
