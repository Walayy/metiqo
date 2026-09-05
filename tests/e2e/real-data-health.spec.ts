import { expect, test } from "@playwright/test";

const metadata = {
  appVersion: "0.1.0",
  asOf: "2026-09-05T12:00:00Z",
  computedAt: "2026-09-05T12:00:00Z",
  dataMode: "real",
  freshness: "degraded",
};

function pageResponse(data: readonly unknown[]) {
  return {
    data,
    meta: metadata,
    page: { limit: 100, offset: 0, total: data.length },
  };
}

test("renders real fixture provenance without replacing the mock UI", async ({ page }) => {
  await page.route("**/api/backend/api/v1/admin/data-sources**", async (route) => {
    await route.fulfill({
      body: JSON.stringify(
        pageResponse([
          {
            checkedAt: "2026-09-05T12:00:00Z",
            detail: "Dernier snapshot validé conservé malgré un incident plus récent",
            lastSuccessAt: "2026-09-05T10:00:00Z",
            providerCode: "oracles_elixir",
            status: "degraded",
          },
        ]),
      ),
      contentType: "application/json",
    });
  });
  await page.route("**/api/backend/api/v1/admin/ingestion-runs**", async (route) => {
    await route.fulfill({
      body: JSON.stringify(
        pageResponse([
          {
            completedAt: "2026-09-05T10:00:00Z",
            dataMode: "real",
            errorCode: null,
            lastValidSnapshotId: "11111111-1111-4111-8111-111111111111",
            maxEventDate: "2026-08-31T00:00:00Z",
            minEventDate: "2026-01-10T00:00:00Z",
            rowCount: 123456,
            runId: "22222222-2222-4222-8222-222222222222",
            runKind: "sync",
            schemaChanged: false,
            schemaFingerprint: "c".repeat(64),
            seasonYear: 2026,
            snapshotSha256: "a".repeat(64),
            source: "oracles_elixir/2026",
            startedAt: "2026-09-05T09:59:00Z",
            status: "succeeded",
            transport: "google-drive-public",
          },
        ]),
      ),
      contentType: "application/json",
    });
  });
  await page.route("**/api/backend/api/v1/admin/quality-issues**", async (route) => {
    await route.fulfill({
      body: JSON.stringify(
        pageResponse([
          {
            code: "UNEXPECTED_HTML",
            dataMode: "real",
            detail: "Snapshot isolé ; le dernier snapshot validé reste publié",
            issueId: "33333333-3333-4333-8333-333333333333",
            observedAt: "2026-09-05T11:00:00Z",
            severity: "blocking",
            source: "oracles_elixir/2026",
            status: "quarantined",
          },
        ]),
      ),
      contentType: "application/json",
    });
  });

  await page.goto("/data");

  await expect(page.getByRole("region", { name: "Catalogue des sources" })).toContainText(
    "oracles_elixir",
  );
  const snapshot = page.getByRole("region", { name: "Snapshot et couverture" });
  await expect(snapshot).toContainText("123456");
  await expect(snapshot).toContainText("a".repeat(64));
  await expect(snapshot).toContainText("c".repeat(64));
  await expect(snapshot).toContainText("stable");
  await expect(snapshot).toContainText("2026");
  await expect(page.getByRole("region", { name: "Quarantaine" })).toContainText("UNEXPECTED_HTML");
});
