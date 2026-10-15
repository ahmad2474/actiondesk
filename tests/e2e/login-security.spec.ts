import { randomUUID } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { test, expect, type Page } from "@playwright/test";

const fixture = process.env.BROWSER_API_URL;
type Credentials = { email: string; password: string };

// Store only violation labels, never credential-bearing URLs, titles or bodies.
function watchCredentials(page: Page, credentials: Credentials) {
  const violations: string[] = [];
  const submissions: { method: string; path: string }[] = [];
  const contains = (value: string) => [credentials.email, credentials.password].some(secret =>
    value.includes(secret) || value.includes(encodeURIComponent(secret)) || value.includes(new URLSearchParams({ v: secret }).toString().slice(2)));
  function checkURL(value: string) {
    const url = new URL(value);
    if (contains(value) || ["email", "password"].some(key => url.searchParams.has(key))) violations.push("credential in URL");
  }
  page.on("request", request => {
    checkURL(request.url());
    if (contains(request.headers().referer ?? "")) violations.push("credential in referrer");
    const body = request.postData() ?? "";
    if (contains(body)) {
      const path = new URL(request.url()).pathname;
      submissions.push({ method: request.method(), path });
      if (request.method() !== "POST" || !["/api/actiondesk/auth/login", "/api/actiondesk/login-unavailable"].includes(path)) violations.push("credential outside intended POST");
    }
  });
  page.on("framenavigated", frame => { if (frame === page.mainFrame()) checkURL(frame.url()); });
  page.on("response", response => {
    if (contains(response.headers().location ?? "")) violations.push("credential in redirect");
  });
  page.on("console", message => { if (contains(message.text())) violations.push("credential in console"); });
  page.on("pageerror", error => { if (contains(error.message)) violations.push("credential in client error"); });
  return {
    submissions,
    async assertSafe() {
      checkURL(page.url());
      if (contains(await page.title())) violations.push("credential in title");
      for (const file of [".local/web-checks/web.log", ".local/web-checks/api.log"]) {
        if (existsSync(file) && contains(readFileSync(file, "utf8"))) violations.push("credential in test server log");
      }
      expect(violations).toEqual([]);
    },
  };
}

async function fill(page: Page, credentials: Credentials) {
  const form = page.locator("form.login-form");
  await expect(form).toHaveAttribute("method", "post");
  await expect(form).toHaveAttribute("action", "/api/actiondesk/login-unavailable");
  await expect(page.getByLabel("Email address")).toHaveAttribute("autocomplete", "username");
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("autocomplete", "current-password");
  await page.getByLabel("Email address").fill(credentials.email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
}

test.describe("hydrated login credential safety", () => {
  test.skip(!fixture, "Requires the disposable real-auth browser API, never development credentials.");
  test.beforeEach(async ({ request }) => {
    await expect.poll(async () => { try { return (await request.get(`${fixture}/health`)).status(); } catch { return 0; } }).toBe(200);
    await request.post(`${fixture}/__browser/reset`);
  });
  for (const trigger of ["click", "Enter"] as const) {
    test(`successful ${trigger} submits JSON POST without credential URLs`, async ({ page, request }) => {
      const credentials: Credentials = await (await request.get(`${fixture}/__browser/credentials`)).json();
      const security = watchCredentials(page, credentials);
      await page.goto("/login");
      // Explicitly establish hydration for the intended fetch path. Native paths are separate tests.
      await page.getByRole("button", { name: "Show password" }).click();
      await expect(page.getByRole("button", { name: "Hide password" })).toBeVisible();
      await page.getByRole("button", { name: "Hide password" }).click();
      await fill(page, credentials);
      const response = page.waitForResponse(response => new URL(response.url()).pathname === "/api/actiondesk/auth/login");
      if (trigger === "click") await page.getByRole("button", { name: "Sign in", exact: true }).click();
      else await page.getByLabel("Password", { exact: true }).press("Enter");
      expect((await response).status()).toBe(200);
      await expect(page.getByRole("heading", { name: /Welcome back/ })).toBeVisible();
      await expect(page).toHaveURL("/");
      expect(security.submissions).toEqual([{ method: "POST", path: "/api/actiondesk/auth/login" }]);
      await security.assertSafe();
    });
  }
  test("failed login stays on the safe URL and announces a generic error", async ({ page, request }) => {
    const valid: Credentials = await (await request.get(`${fixture}/__browser/credentials`)).json();
    const credentials = { email: valid.email, password: randomUUID() };
    const security = watchCredentials(page, credentials);
    await page.goto("/login");
    await page.getByRole("button", { name: "Show password" }).click();
    await expect(page.getByRole("button", { name: "Hide password" })).toBeVisible();
    await page.getByRole("button", { name: "Hide password" }).click();
    await fill(page, credentials);
    const response = page.waitForResponse(response => new URL(response.url()).pathname === "/api/actiondesk/auth/login");
    await page.getByLabel("Password", { exact: true }).press("Enter");
    expect((await response).status()).toBe(401);
    await expect(page.locator("form.login-form").getByRole("alert")).toContainText("Check your email and password");
    await expect(page).toHaveURL("/login");
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
    expect(security.submissions).toEqual([{ method: "POST", path: "/api/actiondesk/auth/login" }]);
    await security.assertSafe();
  });
});

const synthetic = () => ({ email: `unhydrated-${randomUUID()}@actiondesk.ahmad`, password: randomUUID() });
async function assertFallbackState(page: Page, security: ReturnType<typeof watchCredentials>) {
  await expect(page).toHaveURL("/login?reason=javascript");
  await expect(page.locator("form.login-form").getByRole("alert")).toContainText("Sign-in did not run");
  await expect(page).toHaveTitle("Sign in · ActionDesk");
  expect(security.submissions).toEqual([{ method: "POST", path: "/api/actiondesk/login-unavailable" }]);
  expect((await page.context().cookies()).some(cookie => cookie.name.includes("actiondesk_session"))).toBe(false);
  await security.assertSafe();
}

async function assertFallback(page: Page, security: ReturnType<typeof watchCredentials>) {
  await assertFallbackState(page, security);
  // Revisit both safe document states explicitly. History traversal can race
  // hydration/popstate restoration of the interrupted pre-hydration document.
  await page.goto("/login");
  await expect(page).toHaveURL("/login");
  await expect(page).toHaveTitle("Sign in · ActionDesk");
  await security.assertSafe();
  await page.goto("/login?reason=javascript");
  await assertFallbackState(page, security);
}

test.describe("JavaScript unavailable", () => {
  test.use({ javaScriptEnabled: false });
  for (const trigger of ["click", "Enter"] as const) {
    test(`native ${trigger} fails safely using POST`, async ({ page }) => {
      const credentials = synthetic();
      const security = watchCredentials(page, credentials);
      await page.goto("/login");
      await fill(page, credentials);
      if (trigger === "click") await page.getByRole("button", { name: "Sign in", exact: true }).click();
      else await page.getByLabel("Password", { exact: true }).press("Enter");
      await assertFallback(page, security);
    });
  }
});

test("failed client chunks cannot fall back to credential-bearing GET", async ({ page }) => {
  const credentials = synthetic();
  const security = watchCredentials(page, credentials);
  await page.route("**/_next/static/**", route => route.request().resourceType() === "script" ? route.abort("failed") : route.continue());
  await page.goto("/login");
  await fill(page, credentials);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await assertFallback(page, security);
});

test("submission while hydration scripts are delayed fails safely", async ({ page }) => {
  const credentials = synthetic();
  const security = watchCredentials(page, credentials);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/_next/static/**", async route => {
    if (route.request().resourceType() === "script") await gate;
    await route.continue().catch(() => {}); // Navigation can cancel the old document's requests.
  });
  try {
    await page.goto("/login", { waitUntil: "commit" });
    await fill(page, credentials);
    await page.getByLabel("Password", { exact: true }).press("Enter", { noWaitAfter: true });
    await expect(page).toHaveURL("/login?reason=javascript");
  } finally { release(); }
  await assertFallback(page, security);
});
