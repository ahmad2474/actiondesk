import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, matchesDetail, matchesRequest, pageOffset, readDetailSnapshot, readOwnedCapabilities } from "../../apps/web/lib/read-models.ts";
import { allowedRead, readTarget, sessionCookies } from "../../apps/web/lib/transport.ts";

const record = { id: "request", version: 4, department_id: "department", approvals: [{ id: "manager-step", step: 1, status: "pending" }, { id: "finance-step", step: 2, status: "pending" }] };
const caps = { request_id: "request", expected_version: 4, department: { id: "department", name: "Operations" }, participants: [], available_actions: [{ action: "approve", approval_id: "manager-step" }] };

test("only the approved read paths are admitted; mutations and directories stay closed", () => {
  const id = "00000000-0000-4000-8000-000000000001";
  for (const path of ["auth/me", "requests", "requests/options", `requests/${id}`, `requests/${id}/capabilities`, `requests/${id}/revisions`, `requests/${id}/lifecycle`, ...["approvals", "reversals", "service_work", "finance_processing"].map(queue => `work-queues/${queue}`)]) assert.equal(allowedRead(path), true, path);
  for (const path of ["users", "departments", "policies", "auth/login", `requests/${id}/transitions`, "requests/options/extra", "work-queues/admin", "requests/../../users", "https://example.org/requests"]) assert.equal(allowedRead(path), false, path);
});
test("both adapters force owned scope and forward only bounded read pagination inputs", () => {
  const url = readTarget("requests", new URLSearchParams("scope=organization&limit=20&offset=40&actor_id=foreign&organization_id=foreign&destination=https://example.org"));
  assert.deepEqual(Object.fromEntries(url.searchParams), { scope: "mine", limit: "20", offset: "40" });
  assert.deepEqual(Object.fromEntries(readTarget("work-queues/approvals", new URLSearchParams("scope=all&limit=20&offset=0")).searchParams), { limit: "20", offset: "0" });
  assert.throws(() => readTarget("users", new URLSearchParams()));
  assert.equal(sessionCookies("unrelated=secret; actiondesk_session_local=opaque; actor_id=forged"), "actiondesk_session_local=opaque");
});
test("page offsets reject unbounded or malformed inputs", () => {
  for (const value of [undefined, "-1", "NaN", "1e6", "1000001", "2.5"]) assert.equal(pageOffset(value), 0);
  assert.equal(pageOffset("40"), 40);
});
test("matching versions alone cannot substitute another request or department", () => {
  assert.equal(matchesRequest(record, caps), true);
  for (const changed of [{ request_id: "foreign" }, { expected_version: 5 }, { department: { id: "foreign" } }]) assert.equal(matchesRequest(record, { ...caps, ...changed }), false);
});
test("approval bindings must reference the current pending evidence, never a later step", () => {
  assert.equal(matchesDetail(record, caps), true);
  for (const id of [null, "missing", "finance-step"]) assert.equal(matchesDetail(record, { ...caps, available_actions: [{ action: "approve", approval_id: id }] }), false);
});
test("revision, reversal and resolution bindings must match supplied current evidence", () => {
  const detail = { ...record, proposed_revision: { id: "revision" }, active_reversal: { id: "reversal" }, current_resolution: { id: "resolution" } };
  for (const [action, field, id] of [["resubmit", "revision_id", "revision"], ["approve_reversal", "reversal_request_id", "reversal"], ["reject_reversal", "reversal_request_id", "reversal"], ["create_correction", "reversal_request_id", "reversal"], ["reopen", "resolution_id", "resolution"]]) {
    assert.equal(matchesDetail(detail, { ...caps, available_actions: [{ action, [field]: id }] }), true);
    assert.equal(matchesDetail(detail, { ...caps, available_actions: [{ action, [field]: "old" }] }), false);
  }
  assert.equal(matchesDetail(record, { ...caps, available_actions: [{ action: "reopen", resolution_id: null }] }), true);
});
test("duplicate/internal actions and unauthorized choice contexts fail closed", () => {
  for (const actions of [[...caps.available_actions, ...caps.available_actions], [{ action: "route" }], [{ action: "cancel", approval_id: "manager-step" }]]) assert.equal(matchesDetail(record, { ...caps, available_actions: actions }), false);
  assert.equal(matchesDetail(record, { ...caps, assignee_choices: { items: [{ id: "member", name: "Member" }] } }), false);
  assert.equal(matchesDetail(record, { ...caps, available_actions: [{ action: "assign" }], assignee_choices: { items: [] } }), true);
});
test("a mismatch causes one fresh pair of reads and returns only the matching pair", async () => {
  const calls = [];
  let capabilityReads = 0;
  const result = await readDetailSnapshot(async path => {
    calls.push(path);
    if (!path.includes("capabilities")) return record;
    return { ...caps, expected_version: ++capabilityReads === 1 ? 3 : 4 };
  }, "request", 20);
  assert.equal(result.state, "ready"); assert.equal(result.capabilities.expected_version, 4);
  assert.equal(calls.length, 4); assert.equal(calls.filter(path => path.endsWith("limit=20&offset=20")).length, 2);
});
test("persistent mismatch stops refreshing and discards every capability display/choice value", async () => {
  let calls = 0;
  const result = await readDetailSnapshot(async path => { calls++; return path.includes("capabilities") ? { ...caps, expected_version: 3, participants: [{ id: "old", name: "Stale person" }] } : record; }, "request");
  assert.equal(calls, 4); assert.equal(result.state, "stale"); assert.equal(result.capabilities, null);
});
test("non-access capability failure preserves detail with unavailable actions", async () => {
  const result = await readDetailSnapshot(async path => { if (path.includes("capabilities")) throw new ApiError(503); return record; }, "request");
  assert.equal(result.record, record); assert.equal(result.state, "unavailable"); assert.equal(result.capabilities, null);
});
for (const status of [401, 403, 404]) test(`capability ${status} discards detail rather than displaying revoked content`, async () => {
  await assert.rejects(readDetailSnapshot(async path => { if (path.includes("capabilities")) throw new ApiError(status); return record; }, "request"), error => error.status === status);
});
test("detail read failure and wrong request identity cannot fall back to capability data", async () => {
  await assert.rejects(readDetailSnapshot(async path => { if (!path.includes("capabilities")) throw new ApiError(404); return caps; }, "request"), error => error.status === 404);
  await assert.rejects(readDetailSnapshot(async path => path.includes("capabilities") ? caps : { ...record, id: "foreign" }, "request"), error => error.status === 404);
});
test("owned-list enrichment suppresses stale/failed availability and fails closed on access loss", async () => {
  const stale = { ...record, id: "second" }, missing = { ...record, id: "third" };
  const result = await readOwnedCapabilities(async path => { if (path.includes("third")) throw new ApiError(503); return caps; }, [record, stale, missing]);
  assert.deepEqual(result, { request: caps, second: null, third: null });
  await assert.rejects(readOwnedCapabilities(async () => { throw new ApiError(403); }, [record]), error => error.status === 403);
});
