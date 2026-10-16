import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { Auth, User, RequestDetail, Capabilities, WorkQueue, QueueKind, Revisions, Lifecycle, CreationOptions } from "../../apps/web/lib/api-types";
import { checkScreenshot } from "./visual.js";

const api = process.env.BROWSER_API_URL;
const id = "00000000-0000-4000-8000-000000000061";
const department = "00000000-0000-4000-8000-000000000062";
const reviewer = "00000000-0000-4000-8000-000000000063";
const approval = "00000000-0000-4000-8000-000000000064";
const now = "2026-10-15T10:00:00Z";
type ReadFixtures = Record<string, { status?: number; body?: unknown; hold?: boolean }[]>;
async function configure(request: APIRequestContext, fixtures: ReadFixtures) {
  expect((await request.post(`${api}/__browser/reads`, { data: fixtures })).status()).toBe(200);
}
function data(user: User) {
  const record: RequestDetail = {
    id, organization_id: user.organization_id, created_by: user.id, department_id: department,
    type: "expense", title: "Scoped equipment request", raw_text: "Synthetic authorized intake", status: "MANAGER_REVIEW", version: 3,
    created_at: now, updated_at: now, leave_overlap: false, current_submission_sequence: 2,
    structured_fields: { vendor: "Synthetic supplier", amount: "9007199254740991.99", currency: "PKR", purpose: "Synthetic equipment" },
    approvals: [{ id: approval, step: 1, approver_id: null, approver_role: "manager", status: "pending", candidates: [reviewer], decision: null }],
    status_history: [{ id: approval, request_id: id, sequence: 3, actor_id: reviewer, action: "route", from_state: "SUBMITTED", to_state: "MANAGER_REVIEW", reason: "Synthetic recorded routing", at: now }],
  };
  const capabilities: Capabilities = {
    request_id: id, expected_version: 3, evaluated_at: now, organization_timezone: "Asia/Karachi",
    department: { id: department, name: "Scoped Operations" }, participants: [{ id: user.id, name: "Authorized requester" }, { id: reviewer, name: "Authorized reviewer" }],
    available_actions: ["approve", "reject", "request_changes"].map(action => ({ action: action as "approve" | "reject" | "request_changes", approval_id: approval })), blocking: [], assignee_choices: null,
  };
  const revisions: Revisions = { items: [], submissions: [{ sequence: 2, routing_sequence: 3, revision_id: approval, policy_id: approval, policy_version: 1, policy_definition: { internal_rule: "PRIVATE_POLICY_SENTINEL" }, leave_overlap: false, approvals: record.approvals }], change_requests: [], limit: 20, offset: 0 };
  const lifecycle: Lifecycle = { resolutions: [], reopenings: [], reversal_requests: [], reversal_decisions: [], limit: 20, offset: 0 };
  const reads: ReadFixtures = {
    [`/requests/${id}`]: [{ body: record }], [`/requests/${id}/capabilities`]: [{ body: capabilities }],
    [`/requests/${id}/revisions`]: [{ body: revisions }], [`/requests/${id}/lifecycle`]: [{ body: lifecycle }],
    "/requests": [{ body: { items: [record], limit: 20, offset: 0 } }],
  };
  function queue(kind: QueueKind, actions = capabilities.available_actions): WorkQueue {
    return { queue: kind, organization_timezone: "Asia/Karachi", evaluated_at: now, limit: 20, offset: 0, has_more: false, items: [{
      id, type: record.type, title: record.title, status: record.status, version: record.version,
      requester: capabilities.participants[0], department: capabilities.department, assigned_to: null,
      created_at: now, updated_at: now, due_at: null, current_submission_sequence: 2, service_cycle_sequence: null,
      amount: "9007199254740991.99", currency: "PKR", available_actions: actions, blocking: [],
    }] };
  }
  return { record, capabilities, reads, queue };
}
async function login(page: Page): Promise<User> {
  const credentials = await (await page.request.get(`${api}/__browser/credentials`)).json();
  await page.goto("/login");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByRole("button", { name: "Hide password" })).toBeVisible();
  await page.getByLabel("Email address").fill(credentials.email);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Welcome back/ })).toBeVisible();
  const auth: Auth = await (await page.request.get("/api/actiondesk/auth/me")).json();
  return auth.user;
}
async function accessible(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
}

test.describe("authoritative frontend read integration", () => {
  test.skip(!api, "Requires the disposable browser API, never development credentials.");
  test.beforeEach(async ({ request }) => { await request.post(`${api}/__browser/reset`); });
  test.afterEach(async ({ request }) => { await request.post(`${api}/__browser/reads/release`); });

  test("real read adapter admits scoped reads and still blocks mutation/directory paths", async ({ page }) => {
    await login(page);
    const list = await (await page.request.get("/api/actiondesk/requests?scope=participant&limit=1")).json();
    const requestId: string = list.items[0].id;
    for (const path of [`requests/${requestId}/capabilities`, "requests/options", "work-queues/approvals", "work-queues/reversals", "work-queues/service_work", "work-queues/finance_processing"]) {
      const response = await page.request.get(`/api/actiondesk/${path}`);
      expect(response.status()).toBe(200); expect(response.headers()["cache-control"]).toBe("no-store");
    }
    for (const path of ["requests", `requests/${requestId}/transitions`, "requests/options", "work-queues/approvals"]) expect((await page.request.post(`/api/actiondesk/${path}`, { data: {} })).status()).toBe(404);
    for (const path of ["users", "departments", "policies", "work-queues/admin", `requests/${department}/capabilities`]) expect((await page.request.get(`/api/actiondesk/${path}`)).status()).toBe(404);
    await page.goto("/requests");
    const first = page.locator(".request-table:visible .request-title, .request-cards:visible .request-title").first();
    await first.click(); await expect(page.getByText("Read-only view", { exact: true })).toBeVisible();
  });

  test("matched detail displays only supplied actions, participant names and department", async ({ page, request }, info) => {
    const user = await login(page), fixture = data(user);
    // Backend participant visibility, rather than an owner/role test in the UI.
    fixture.record.created_by = department; fixture.capabilities.participants[0].id = department;
    await configure(request, fixture.reads);
    const writes: string[] = [], directories: string[] = [];
    page.on("request", req => { if (req.method() !== "GET" && req.url().includes("/api/actiondesk/")) writes.push(req.method()); if (/\/api\/actiondesk\/(users|departments|policies)/.test(req.url())) directories.push("directory"); });
    await page.goto(`/requests/${id}`);
    await expect(page.locator(".detail-meta")).toContainText("Authorized requester");
    await expect(page.locator(".detail-meta")).toContainText("Scoped Operations");
    await expect(page.locator("#history")).toContainText("Authorized reviewer");
    for (const name of ["Approve", "Reject", "Request changes"]) await expect(page.locator(".workflow-panel").getByRole("button", { name, exact: true })).toBeDisabled();
    for (const name of ["Process expense", "Assign", "Reopen service", "Resubmit"]) await expect(page.locator(".workflow-panel").getByRole("button", { name, exact: true })).toHaveCount(0);
    expect(await page.content()).not.toContain("PRIVATE_POLICY_SENTINEL");
    await accessible(page); await checkScreenshot(page, info, "read-detail.png");
    expect(writes).toEqual([]); expect(directories).toEqual([]);
  });

  test("role unions and approved status never invent processing or review authority", async ({ page, request }) => {
    const user = await login(page); expect(user.roles).toEqual(expect.arrayContaining(["employee", "manager", "finance"]));
    const fixture = data(user); fixture.record.status = "APPROVED"; fixture.capabilities.available_actions = [];
    await configure(request, fixture.reads); await page.goto(`/requests/${id}`);
    await expect(page.locator(".workflow-panel")).toContainText("No actions are currently available");
    await expect(page.locator(".action-availability button")).toHaveCount(0);
    await expect(page.locator("#service-assignee")).toHaveCount(0);
  });

  test("owned requests use matching capabilities and preserve partial/empty states", async ({ page, request }) => {
    const fixture = data(await login(page)); await configure(request, fixture.reads);
    await page.goto("/requests");
    const visible = page.locator(".request-table:visible, .request-cards:visible");
    await expect(visible).toContainText("Scoped Operations"); await expect(visible.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
    fixture.reads[`/requests/${id}/capabilities`] = [{ status: 503 }]; await configure(request, fixture.reads); await page.reload();
    await expect(visible).toContainText("Scoped equipment request"); await expect(visible).toContainText("Availability could not be matched or loaded");
    fixture.reads["/requests"] = [{ body: { items: [], limit: 20, offset: 0 } }]; await configure(request, fixture.reads); await page.reload();
    await expect(page.getByRole("heading", { name: "Your next request starts here" })).toBeVisible();
  });

  test("approval and reversal queues render server actions independently", async ({ page, request }, info) => {
    const fixture = data(await login(page));
    const decisions = fixture.queue("approvals"); decisions.has_more = true;
    await configure(request, { "/work-queues/approvals": [{ body: decisions }], "/work-queues/reversals": [{ body: fixture.queue("reversals", [{ action: "reject_reversal", reversal_request_id: approval }]) }] });
    await page.goto("/approvals");
    const decisionsView = page.getByRole("region", { name: "Approval decisions", exact: true });
    await expect(decisionsView.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Deny reversal", exact: true })).toBeDisabled();
    await expect(decisionsView.getByRole("link", { name: "Next", exact: true })).toHaveAttribute("href", "/approvals?reversalOffset=0&offset=20");
    await accessible(page); await checkScreenshot(page, info, "read-approvals.png");
    await configure(request, { "/work-queues/approvals": [{ status: 503 }], "/work-queues/reversals": [{ body: fixture.queue("reversals", [{ action: "reject_reversal", reversal_request_id: approval }]) }] });
    await page.reload(); await expect(page.locator(".error-state[role=alert]")).toContainText("Connection unavailable"); await expect(page.getByRole("button", { name: "Deny reversal", exact: true })).toBeDisabled();
  });

  test("service and finance queues display scoped work and processing holds", async ({ page, request }, info) => {
    const fixture = data(await login(page));
    const service = fixture.queue("service_work", [{ action: "start" }, { action: "resolve" }]);
    service.items[0] = { ...service.items[0], type: "service", title: "Scoped cooling repair", status: "IN_PROGRESS", amount: null, assigned_to: { id: reviewer, name: "Authorized assignee" } };
    const finance = fixture.queue("finance_processing", []); finance.items[0].blocking = [{ action: "process", code: "reversal_review", message: "Processing is on hold during reversal review." }];
    finance.items.push({ ...finance.items[0], id: department, title: "Approved equipment", available_actions: [{ action: "process" }], blocking: [] });
    await configure(request, { "/work-queues/service_work": [{ body: service }], "/work-queues/finance_processing": [{ body: finance }] });
    await page.goto("/service-work"); await expect(page.getByRole("button", { name: "Start work", exact: true })).toBeDisabled(); await expect(page.getByRole("button", { name: "Resolve", exact: true })).toBeDisabled();
    await expect(page.locator(".live-queue")).toContainText("Authorized assignee"); await accessible(page); await checkScreenshot(page, info, "read-service.png");
    await page.goto("/finance-processing"); const held = page.locator("article").filter({ hasText: "Scoped equipment request" });
    await expect(held).toContainText("Processing is on hold"); await expect(held.getByRole("button", { name: "Process expense", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Process expense", exact: true })).toBeDisabled(); await expect(page.locator("article").first()).toContainText("PKR 9,007,199,254,740,991.99");
    await accessible(page); await checkScreenshot(page, info, "read-finance.png");
  });

  test("authorized department and assignee choices are paged and never submit", async ({ page, request }, info) => {
    const fixture = data(await login(page)); fixture.record.type = "service"; fixture.record.status = "TRIAGED"; fixture.capabilities.available_actions = [{ action: "assign" }];
    fixture.capabilities.assignee_choices = { items: [{ id: reviewer, name: "Scoped service member" }], limit: 20, offset: 0, has_more: true };
    const options: CreationOptions = { organization_timezone: "Asia/Karachi", request_types: ["service", "leave"], departments: { items: [{ id: department, name: "Scoped Operations" }], limit: 20, offset: 0, has_more: true } };
    await configure(request, { ...fixture.reads, "/requests/options": [{ body: options }], "/requests/options?limit=20&offset=20": [{ body: { ...options, departments: { items: [{ id: reviewer, name: "Next scoped department" }], offset: 20, limit: 20, has_more: false } } }], [`/requests/${id}/capabilities?limit=20&offset=20`]: [{ body: { ...fixture.capabilities, assignee_choices: { items: [{ id: approval, name: "Next scoped member" }], offset: 20, limit: 20, has_more: false } } }] });
    const writes: string[] = []; page.on("request", req => { if (req.method() !== "GET" && req.url().includes("/api/actiondesk/")) writes.push(req.method()); });
    await page.goto(`/requests/${id}`); await expect(page.getByLabel("Eligible assignees · read-only", { exact: true })).toBeDisabled();
    await expect(page.locator(".choice-labels")).toHaveText("Scoped service member"); await page.getByRole("link", { name: "More choices", exact: true }).click();
    await expect(page.locator(".choice-labels")).toHaveText("Next scoped member");
    await page.goto("/requests/new"); await expect(page.getByLabel("Department choices · read-only", { exact: true })).toBeDisabled();
    await expect(page.locator("#request-type option")).toHaveText(["Available types", "service", "leave"]);
    await expect(page.getByRole("link", { name: "More choices", exact: true })).toHaveAttribute("href", "/requests/new?departmentOffset=20");
    await accessible(page); await checkScreenshot(page, info, "read-options.png");
    await page.getByRole("link", { name: "More choices", exact: true }).click(); await expect(page.getByRole("list", { name: "Department choices", exact: true })).toHaveText("Next scoped department");
    await configure(request, { "/requests/options": [{ body: { ...options, request_types: [], departments: { items: [], limit: 20, offset: 0, has_more: false } } }] });
    await page.goto("/requests/new"); await expect(page.getByText("No request types are available.")).toBeVisible(); await expect(page.getByText("No choices on this page.")).toBeVisible();
    await configure(request, { "/requests/options": [{ status: 503 }] }); await page.reload(); await expect(page.locator(".error-state[role=alert]")).toContainText("Connection unavailable");
    expect(writes).toEqual([]);
  });

  test("one fresh read repairs a mismatch; persistent stale bindings suppress names and actions", async ({ page, request }) => {
    const fixture = data(await login(page)); const stale = { ...fixture.capabilities, expected_version: 2, participants: [{ id: reviewer, name: "STALE_NAME_SENTINEL" }] };
    fixture.reads[`/requests/${id}/capabilities`] = [{ body: stale }, { body: fixture.capabilities }];
    await configure(request, fixture.reads); await page.goto(`/requests/${id}`); await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
    fixture.reads[`/requests/${id}/capabilities`] = [{ body: stale }]; await configure(request, fixture.reads); await page.reload();
    await expect(page.locator(".workflow-panel")).toContainText("The request changed while loading"); await expect(page.locator(".action-availability button")).toHaveCount(0);
    expect(await page.content()).not.toContain("STALE_NAME_SENTINEL"); await expect(page.getByRole("link", { name: "Refresh current request" })).toBeVisible();
    fixture.reads[`/requests/${id}/capabilities`] = [{ body: { ...fixture.capabilities, available_actions: [{ action: "approve", approval_id: department }] } }];
    await configure(request, fixture.reads); await page.reload(); await expect(page.locator(".workflow-panel")).toContainText("The request changed while loading");
  });

  test("capability and evidence API failures keep only authorized partial detail", async ({ page, request }) => {
    const fixture = data(await login(page)); fixture.reads[`/requests/${id}/capabilities`] = [{ status: 503 }]; fixture.reads[`/requests/${id}/revisions`] = [{ status: 503 }];
    await configure(request, fixture.reads); await page.goto(`/requests/${id}`);
    await expect(page.getByRole("heading", { name: "Scoped equipment request" })).toBeVisible();
    await expect(page.locator(".workflow-panel")).toContainText("Action availability and participant names could not be loaded");
    await expect(page.getByText(/Some evidence could not be loaded/)).toBeVisible(); await expect(page.locator("#history")).not.toContainText("Authorized reviewer");
  });

  test("revision, reversal and service-cycle actions stay non-mutating", async ({ page, request }) => {
    const fixture = data(await login(page));
    const writes: string[] = []; page.on("request", req => { if (req.method() !== "GET" && req.url().includes("/api/actiondesk/")) writes.push(req.method()); });
    fixture.record.status = "NEEDS_INFO";
    fixture.record.proposed_revision = { id: approval, actor_id: fixture.record.created_by, at: now, event_sequence: 3, change_sequence: 2, predecessor_id: null, kind: "proposed", schema_version: 1, fields: {}, clarification: "Synthetic correction" };
    fixture.capabilities.available_actions = [{ action: "revise" }, { action: "resubmit", revision_id: approval }];
    await configure(request, fixture.reads); await page.goto(`/requests/${id}`);
    for (const name of ["Revise", "Resubmit"]) await expect(page.locator(".workflow-panel").getByRole("button", { name, exact: true })).toBeDisabled();
    fixture.record.status = "APPROVED"; fixture.capabilities.available_actions = [{ action: "request_reversal" }];
    await configure(request, fixture.reads); await page.reload(); await expect(page.getByRole("button", { name: "Request reversal", exact: true })).toBeDisabled();
    fixture.record.status = "REVERSAL_REVIEW"; fixture.record.active_reversal = { id: approval, request_id: id, submission_sequence: 2, final_decision_id: approval, actor_id: reviewer, event_sequence: 3, intent: "correct", organization_timezone: "Asia/Karachi" };
    fixture.capabilities.available_actions = [{ action: "approve_reversal", reversal_request_id: approval }, { action: "reject_reversal", reversal_request_id: approval }];
    await configure(request, fixture.reads); await page.reload();
    for (const name of ["Accept reversal", "Deny reversal"]) await expect(page.getByRole("button", { name, exact: true })).toBeDisabled();
    fixture.record.status = "REVERSED"; fixture.capabilities.available_actions = [{ action: "create_correction", reversal_request_id: approval }];
    await configure(request, fixture.reads); await page.reload(); await expect(page.getByRole("button", { name: "Create correction draft", exact: true })).toBeDisabled();
    fixture.record.type = "service"; fixture.record.status = "RESOLVED"; fixture.record.service_cycle_sequence = 2;
    fixture.record.current_resolution = { id: approval, actor_id: reviewer, at: now, cycle_sequence: 2, event_sequence: 3, body: "Synthetic resolution", captured_by: null, captured_at: null };
    fixture.capabilities.available_actions = [{ action: "reopen", resolution_id: approval }, { action: "close" }];
    await configure(request, fixture.reads); await page.reload();
    for (const name of ["Reopen service", "Close"]) { const button = page.locator(".workflow-panel").getByRole("button", { name, exact: true }); await expect(button).toBeDisabled(); await button.dispatchEvent("click"); }
    expect(writes).toEqual([]);
  });

  for (const status of [401, 403, 404]) test(`capability ${status} hides the request instead of using cached permissions`, async ({ page, request }) => {
    const fixture = data(await login(page)); fixture.reads[`/requests/${id}/capabilities`] = [{ status }]; await configure(request, fixture.reads); await page.goto(`/requests/${id}`);
    if (status === 401) await expect(page).toHaveURL(/\/login\?reason=expired/);
    else await expect(page.locator(".error-state[role=alert]")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Scoped equipment request" })).toHaveCount(0); expect(await page.content()).not.toContain("Authorized reviewer");
  });
  test("a foreign-tenant detail is never rendered even with matching capability IDs", async ({ page, request }) => {
    const fixture = data(await login(page)); fixture.record.organization_id = department; await configure(request, fixture.reads); await page.goto(`/requests/${id}`);
    await expect(page.locator(".error-state[role=alert]")).toContainText("Request unavailable"); expect(await page.content()).not.toContain("Synthetic authorized intake");
  });
  test("queue loading waits on a deterministic read gate, then renders a real empty state", async ({ page, request }) => {
    const fixture = data(await login(page)); const empty = fixture.queue("service_work"); empty.items = [];
    await configure(request, { "/work-queues/service_work": [{ body: empty, hold: true }] });
    await page.goto("/service-work", { waitUntil: "commit" }); await expect(page.getByText("Loading requests", { exact: true })).toBeVisible();
    await request.post(`${api}/__browser/reads/release`); await expect(page.getByRole("heading", { name: "No work on this page" })).toBeVisible(); await expect(page.locator(".action-availability button")).toHaveCount(0);
  });
});
