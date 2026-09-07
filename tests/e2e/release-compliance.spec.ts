import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

for (const viewport of [
  { width: 1440, height: 1000 },
  { width: 390, height: 844 },
]) {
  test(`shows release refusals and no guaranteed gain at ${String(viewport.width)}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.goto("/settings");
    await expect(page.getByRole("heading", { level: 1, name: "Paramètres" })).toBeVisible();
    const compliance = page.getByRole("region", { name: "Portes de publication" });
    await expect(compliance.getByText("OE-COMMERCIAL : NO-GO", { exact: true })).toBeVisible();
    await expect(compliance.getByText("RIOT-PRODUCT : NO-GO", { exact: true })).toBeVisible();
    await expect(
      compliance.getByText("Publication publique ou commerciale bloquée.", { exact: true }),
    ).toBeVisible();
    await expect(compliance.getByText("Provider Stake désactivé.", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Metiquo ne garantit aucun gain.", { exact: true }).first(),
    ).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.screenshot({
      path: testInfo.outputPath(`compliance-${String(viewport.width)}.png`),
      fullPage: true,
    });
  });
}
