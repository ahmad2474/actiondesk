import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { checkScreenshot } from "./visual.js";

test("login hydrates and intercepts native submission at the configured browser origin", async ({ page }) => {
  const failures: string[] = [];
  page.on("pageerror", () => failures.push("client runtime error"));
  page.on("requestfailed", request => { if (request.resourceType() === "script") failures.push("client chunk failed"); });
  const posts: { method: string; path: string; contentType: string }[] = [];
  await page.route("**/api/actiondesk/auth/login", async route => {
    const request = route.request();
    posts.push({ method: request.method(), path: new URL(request.url()).pathname, contentType: request.headers()["content-type"] });
    await route.fulfill({ status: 401, contentType: "application/problem+json", body: JSON.stringify({ title: "Unauthorized", detail: "Invalid credentials." }) });
  });
  await page.goto("/login");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByRole("button", { name: "Hide password" }), "Client Component must hydrate at the documented loopback URL").toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Hide password" }).click();
  await page.getByLabel("Email address").fill("hydration-check@actiondesk.ahmad");
  await page.getByLabel("Password", { exact: true }).fill("synthetic-browser-probe");
  await page.getByLabel("Password", { exact: true }).press("Enter");
  await expect(page.locator("form.login-form").getByRole("alert")).toContainText("Check your email and password");
  await expect(page).toHaveURL("/login");
  expect(posts).toEqual([{ method: "POST", path: "/api/actiondesk/auth/login", contentType: "application/json" }]);
  expect(failures).toEqual([]);
});

test("sign-in is readable and accessible at every supported width", async ({ page }, info) => {
  await page.goto("/login");
  await expect(page).toHaveTitle("Sign in · ActionDesk");
  await expect(page.getByRole("heading", { name: "Sign in to ActionDesk" })).toBeVisible();
  await expect(page.getByLabel("Email address")).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  await checkScreenshot(page, info, "login.png");
});
