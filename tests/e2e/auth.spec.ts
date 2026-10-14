import { test, expect, type Page } from "@playwright/test";
const fixture = process.env.BROWSER_API_URL;
test.describe("real PostgreSQL session and owned reads", () => {
  test.skip(!fixture, "Set BROWSER_API_URL to the disposable browser API; never use development credentials.");
  test.beforeEach(async ({ request }) => {
    await expect.poll(async () => { try { return (await request.get(`${fixture}/health`)).status(); } catch { return 0; } }, { timeout: 30000 }).toBe(200);
    await request.post(`${fixture}/__browser/reset`);
  });
  async function login(page: Page) {
    const response = await page.request.get(`${fixture}/__browser/credentials`);
    const credentials: { email: string; password: string } = await response.json();
    await page.goto("/login");
    await page.getByLabel("Email address").fill(credentials.email);
    await page.getByLabel("Password", { exact: true }).fill(credentials.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("heading", { name: /Welcome back/ })).toBeVisible();
  }
  test("real sign-in, cookie, pagination, evidence, CSRF logout and no workflow writes", async ({ page, context }) => {
    const writes: string[] = [];
    page.on("request", request => { if (request.method() === "POST" && /\/api\/actiondesk\/requests/.test(request.url())) writes.push(request.url()); });
    await page.goto("/"); await expect(page).toHaveURL(/\/login/);
    await login(page);
    const cookies = await context.cookies();
    expect(cookies.find(cookie => cookie.name === "actiondesk_session_local")?.httpOnly).toBe(true);
    expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
    await page.goto("/requests");
    await expect(page.getByRole("heading", { name: "My Requests", exact: true })).toBeVisible();
    const visible = page.locator(".request-table:visible .request-title, .request-cards:visible .request-title").first();
    await visible.click();
    await expect(page.getByRole("heading", { name: "Current submitted information", exact: true }).or(page.getByRole("heading", { name: "Service information", exact: true }))).toBeVisible();
    await expect(page.getByText("Read-only view", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Activity history" })).toBeVisible();
    await page.goto("/requests?offset=20"); await expect(page.getByRole("link", { name: "Previous", exact: true })).toBeVisible();
    expect(writes).toEqual([]);
    const blocked = await page.request.post("/api/actiondesk/requests/00000000-0000-4000-8000-000000000001/transitions", { data: { action: "approve" } });
    expect(blocked.status()).toBe(404);
    const unprotectedLogout = await page.request.post("/api/actiondesk/auth/logout", { headers: { Origin: "http://127.0.0.1:3100" } });
    expect(unprotectedLogout.status()).toBe(403);
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
    await expect(page).toHaveURL(/\/login/);
    expect(writes).toEqual([]); // APIRequestContext probes are not UI mutations.
    await page.goto("/"); await expect(page).toHaveURL(/\/login/);
  });
  test("expiry removes sensitive content without automatic mutation replay", async ({ page, request }) => {
    await login(page);
    await request.post(`${fixture}/__browser/expire`);
    await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
    await expect(page).toHaveURL(/\/login\?reason=expired/);
    await expect(page.getByRole("status")).toContainText("Your session ended");
    await expect(page.getByRole("heading", { name: /Welcome back/ })).toHaveCount(0);
  });
  test("switching accounts clears old owned content and refreshes identity", async ({ page, request }) => {
    await login(page);
    await page.goto("/requests");
    const records = await page.request.get("/api/actiondesk/requests?limit=20");
    const first = (await records.json()).items[0];
    const next = await request.get(`${fixture}/__browser/credentials/manager`);
    const response = await page.request.post("/api/actiondesk/auth/login", {
      data: await next.json(), headers: { Origin: "http://127.0.0.1:3100" },
    });
    expect(response.status()).toBe(200);
    await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
    await expect(page.getByText("No request was created", { exact: true })).toHaveCount(0);
    await expect(page).toHaveURL("/");
    await page.goto(`/requests/${first.id}`);
    await expect(page.locator(".error-state")).toContainText("Request unavailable");
    await expect(page.getByRole("heading", { name: first.title, exact: true })).toHaveCount(0);
  });
  test("login validation, password visibility, 403/422/429 and network failure", async ({ page, request }) => {
    await page.goto("/login"); await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByText("Enter your email address.")).toBeVisible();
    await expect(page.getByLabel("Email address")).toBeFocused();
    const response = await request.get(`${fixture}/__browser/credentials`);
    const credentials = await response.json();
    await page.getByLabel("Email address").fill(credentials.email);
    await page.getByLabel("Password", { exact: true }).fill(credentials.password);
    await page.getByRole("button", { name: "Show password" }).click();
    await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
    await page.getByRole("button", { name: "Hide password" }).click();
    for (const status of [403, 422, 429]) {
      await request.post(`${fixture}/__browser/fault/${status}`);
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      await expect(page.locator(".form-error")).toContainText(status === 403 ? "security checks failed" : status === 422 ? "could not be accepted" : "Too many");
    }
    await request.post(`${fixture}/__browser/reset`);
    await page.reload();
    await page.getByLabel("Email address").fill(credentials.email);
    await page.getByLabel("Password", { exact: true }).fill(credentials.password);
    await page.route("**/api/actiondesk/auth/login", route => route.abort("failed"));
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.locator(".form-error")).toContainText("Connection unavailable");
  });
  test("live read failures do not invent records or grant access", async ({ page, request }) => {
    await login(page);
    await page.goto("/requests/00000000-0000-4000-8000-000000000000");
    await expect(page.locator(".error-state")).toContainText("Request unavailable");
    for (const status of [403, 409, 422, 503]) {
      await request.post(`${fixture}/__browser/fault/${status}/requests`);
      await page.goto("/requests");
      await expect(page.locator(".error-state")).toBeVisible();
      await request.post(`${fixture}/__browser/clear`);
    }
  });
});
