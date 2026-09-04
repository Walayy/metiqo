import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: true,
  preserveOutput: "always",
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  snapshotPathTemplate: "{testDir}/{testFilePath}-snapshots/{arg}{ext}",
  webServer: [
    {
      command:
        "uv run --frozen uvicorn metiquo.api.app:create_app --factory --host 127.0.0.1 --port 8000",
      env: {
        APP_DATA_MODE: "mock",
        APP_ENV: "test",
        DATABASE_URL: "postgresql+psycopg://metiquo@127.0.0.1:5432/metiquo",
        ODDS_PROVIDER: "mock",
      },
      reuseExistingServer: process.env.CI !== "true",
      timeout: 120_000,
      url: "http://127.0.0.1:8000/health",
    },
    {
      command: "pnpm --filter @metiquo/web build && pnpm --filter @metiquo/web start",
      reuseExistingServer: process.env.CI !== "true",
      timeout: 120_000,
      url: "http://127.0.0.1:3000/health",
    },
  ],
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
