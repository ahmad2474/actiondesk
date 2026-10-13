import { test, expect } from "@playwright/test";
test("foundation page is readable at desktop and mobile widths", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("ActionDesk");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("main")).toContainText("Your internal operations workspace");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
