import { expect, test, type Page, type TestInfo } from "@playwright/test";

type BrowserMessage = Readonly<{
  text: string;
  type: "error" | "pageerror" | "warning";
}>;

function collectBrowserMessages(page: Page) {
  const messages: BrowserMessage[] = [];

  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      messages.push({ text: message.text(), type: message.type() });
    }
  });
  page.on("pageerror", (error) => {
    messages.push({ text: error.message, type: "pageerror" });
  });

  return messages;
}

async function openWithStoredTheme(page: Page, theme: "dark" | "light") {
  await page.addInitScript((storedTheme) => {
    window.localStorage.setItem("metiquo-theme", storedTheme);
  }, theme);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

for (const theme of ["light", "dark"] as const) {
  test(`renders the ${theme} theme before hydration without console warnings`, async ({
    page,
  }, testInfo: TestInfo) => {
    const messages = collectBrowserMessages(page);

    await openWithStoredTheme(page, theme);
    await expect(page.getByRole("heading", { level: 1, name: "Opportunités" })).toBeVisible();
    await expect(page.locator("aside").getByText("MOCK", { exact: true })).toBeVisible();

    const renderedTheme = await page.locator("html").evaluate((element) => {
      const styles = window.getComputedStyle(element);
      return {
        backgroundColor: styles.backgroundColor,
        colorScheme: styles.colorScheme,
      };
    });
    expect(renderedTheme.colorScheme).toBe(theme);
    expect(renderedTheme.backgroundColor).not.toBe("rgba(0, 0, 0, 0)");

    const screenshotPath = testInfo.outputPath(`shell-${theme}.png`);
    await page.screenshot({ fullPage: true, path: screenshotPath });
    await testInfo.attach(`shell-${theme}`, {
      contentType: "image/png",
      path: screenshotPath,
    });

    expect(messages).toEqual([]);
  });
}

test("follows the operating system theme on first visit", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("keeps desktop navigation complete and keyboard reachable", async ({ page }) => {
  await page.goto("/");

  const navigation = page.getByRole("navigation", { name: "Navigation principale" });
  await expect(navigation).toBeVisible();
  for (const label of [
    "Opportunités",
    "Événements",
    "Paper trading",
    "Modèles & backtests",
    "Données",
    "Administration",
    "Paramètres",
  ]) {
    await expect(navigation.getByRole("link", { name: label })).toBeVisible();
  }

  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Aller au contenu" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
});

test("opens the mobile navigation and changes routes without a full page shell loss", async ({
  page,
}) => {
  await page.setViewportSize({ height: 844, width: 390 });
  await page.goto("/");

  await expect(page.getByRole("button", { name: "Ouvrir la navigation" })).toBeVisible();
  await page.getByRole("button", { name: "Ouvrir la navigation" }).click();

  const dialog = page.getByRole("dialog", { name: "Navigation" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("link", { name: "Événements" }).click();

  await expect(page).toHaveURL(/\/events$/);
  await expect(page.getByRole("heading", { level: 1, name: "Événements" })).toBeVisible();
  await expect(dialog).toBeHidden();
  await expect(page.locator("header").getByText("MOCK", { exact: true })).toBeVisible();
});

test("changes the theme from the accessible appearance menu", async ({ page }) => {
  await openWithStoredTheme(page, "light");

  await page.getByRole("button", { name: "Changer le thème" }).click();
  await page.getByRole("menuitem", { name: "Sombre" }).click();

  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect
    .poll(() => page.evaluate(() => window.localStorage.getItem("metiquo-theme")))
    .toBe("dark");
});
