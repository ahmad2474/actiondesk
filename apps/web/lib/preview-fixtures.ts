/** Fictional design fixtures. Never merged into authenticated API responses. */
import type { User, RequestRecord, RequestDetail, Revisions, Lifecycle, Status } from "./api-types";
const id = (n: number) => `${n.toString(16).padStart(8, "0")}-0000-4000-8000-${String(n).padStart(12, "0")}`;
export const previewUser: User = { id: id(21), name: "Samira Khan", email: "samira@actiondesk.ahmad", organization_id: id(2), department_id: id(3), roles: ["employee", "manager", "finance"], status: "active", created_at: "2026-10-01T08:00:00Z" };
const base: RequestRecord = { id: id(10), organization_id: id(2), created_by: id(1), department_id: id(3), type: "expense", title: "Replacement workstations for the customer support team", raw_text: "We need replacement workstations for the support team. Please review the purchase for the new starters.", status: "FINANCE_REVIEW", version: 11, created_at: "2026-10-14T09:00:00Z", updated_at: "2026-10-16T11:00:00Z" };
export const previewRecords: RequestRecord[] = ([base, { ...base, id: id(11), title: "Air conditioning in the east meeting room", type: "service", status: "IN_PROGRESS" }, { ...base, id: id(12), title: "Annual leave · family visit", type: "leave", status: "APPROVED" }, { ...base, id: id(13), title: "Travel expense · on-site customer workshop", status: "NEEDS_INFO" }, { ...base, id: id(14), title: "Office supplies for the new support pod", status: "COMPLETED" }] satisfies RequestRecord[]).map(record => ({ ...record, created_by: previewUser.id }));
export function detailFixture(kind: string): { record: RequestDetail; revisions: Revisions; lifecycle: Lifecycle } {
  const fields = { type: "expense", vendor: "Northline Computing", amount: "248500.00", currency: "PKR", purpose: "Four replacement workstations for the customer support team. The corrected quote includes the required warranty.\nDelivery will be coordinated with the office team." };
  const manager = id(20), finance = id(21);
  const at = (sequence: number) => `2026-10-${String(14 + Math.floor(sequence / 6)).padStart(2, "0")}T${String(9 + sequence % 6).padStart(2, "0")}:00:00Z`;
  const event = (sequence: number, action: string, from_state: Status | null, to_state: Status, actor_id = id(1), reason = "Synthetic example for design review.") => ({ id: id(100 + sequence), request_id: base.id, sequence, actor_id, action, from_state, to_state, reason, at: at(sequence) });
  const decision = (step: number, sequence: number) => ({ id: id(300 + sequence), approval_id: id(200 + step), actor_id: step === 1 ? manager : finance, required_role: step === 1 ? "manager" as const : "finance" as const, outcome: "approved", reason: step === 1 ? "The revised quote covers the approved equipment requirements." : "The expense meets the current policy requirements.", at: at(sequence), event_sequence: sequence });
  const steps = [1, 2].map(step => ({ id: id(200 + step), step, approver_id: null, approver_role: step === 1 ? "manager" as const : "finance" as const, status: step === 1 ? "approved" : "pending", candidates: [step === 1 ? manager : finance], decision: step === 1 ? decision(1, 10) : null }));
  const record: RequestDetail = { ...base, leave_overlap: false, structured_fields: fields, current_submission_sequence: 8, approvals: steps, approved_at: null, completed_at: null, status_history: [event(1, "created", null, "DRAFT"), event(2, "submit", "DRAFT", "SUBMITTED"), event(3, "route", "SUBMITTED", "MANAGER_REVIEW"), event(4, "approve", "MANAGER_REVIEW", "FINANCE_REVIEW", manager, "Initial equipment scope approved."), event(5, "request_changes", "FINANCE_REVIEW", "NEEDS_INFO", finance, "Please confirm warranty coverage and provide the final quoted amount."), event(6, "revise", "NEEDS_INFO", "NEEDS_INFO", id(1), "Added the warranty and updated the amount."), event(7, "revise", "NEEDS_INFO", "NEEDS_INFO", id(1), "Confirmed vendor details and corrected the quote reference."), event(8, "resubmit", "NEEDS_INFO", "SUBMITTED"), event(9, "route", "SUBMITTED", "MANAGER_REVIEW"), event(10, "approve", "MANAGER_REVIEW", "FINANCE_REVIEW", manager, decision(1, 10).reason)], version: 10 };
  const revision = (n: number, values = fields) => ({ id: id(400 + n), predecessor_id: n === 2 ? null : id(402), change_sequence: n === 2 ? null : 5, event_sequence: n, actor_id: id(1), at: at(n), kind: n === 2 ? "submitted" : "proposed", schema_version: 1, fields: values, clarification: n === 2 ? "" : "Warranty confirmed with the vendor." });
  const revisions: Revisions = { items: [revision(2, { ...fields, amount: "230000.00" }), revision(7)], submissions: [{ sequence: 2, routing_sequence: 3, revision_id: id(402), policy_id: id(500), policy_version: 1, policy_definition: {}, leave_overlap: false, approvals: [{ ...steps[0], id: id(220), decision: { ...decision(1, 4), approval_id: id(220), reason: "Initial equipment scope approved." } }, { ...steps[1], id: id(221), status: "cancelled" }] }, { sequence: 8, routing_sequence: 9, revision_id: id(407), policy_id: id(501), policy_version: 2, policy_definition: {}, leave_overlap: false, approvals: steps }], change_requests: [{ event_sequence: 5, submission_sequence: 2, approval_id: id(221), actor_id: finance, required_role: "finance" }], limit: 20, offset: 0 };
  const lifecycle: Lifecycle = { reversal_requests: [], reversal_decisions: [], resolutions: [], reopenings: [], limit: 20, offset: 0 };
  if (["approved", "reversal", "reversed"].includes(kind)) {
    record.approvals = [steps[0], { ...steps[1], status: "approved", decision: decision(2, 11) }];
    record.status = "APPROVED"; record.version = 11; record.approved_at = at(11);
    revisions.submissions[1].approvals = record.approvals;
    record.status_history.push(event(11, "approve", "FINANCE_REVIEW", "APPROVED", finance, decision(2, 11).reason));
    if (kind !== "approved") {
      record.status = "REVERSAL_REVIEW"; record.version = 12;
      record.status_history.push(event(12, "request_reversal", "APPROVED", "REVERSAL_REVIEW", id(1), "The vendor can no longer supply this model. Requesting a correction through a new linked request."));
      record.active_reversal = { id: id(600), request_id: record.id, submission_sequence: 8, final_decision_id: id(311), actor_id: id(1), event_sequence: 12, intent: "correct", organization_timezone: "Asia/Karachi" };
      lifecycle.reversal_requests = [record.active_reversal];
      if (kind === "reversed") {
        record.status = "REVERSED"; record.version = 13; record.replacement_request_id = id(700);
        record.status_history.push(event(13, "approve_reversal", "REVERSAL_REVIEW", "REVERSED", finance, "Accepted correction reversal. Original approvals are retained as historical evidence."));
        lifecycle.reversal_decisions = [{ id: id(601), reversal_request_id: id(600), actor_id: finance, event_sequence: 13, outcome: "accepted", organization_timezone: "Asia/Karachi" }];
      }
    }
  }
  if (kind === "changes") {
    record.status = "NEEDS_INFO"; record.version = 7; record.current_submission_sequence = 2;
    record.status_history = record.status_history.filter(item => item.sequence <= 7);
    record.approvals = revisions.submissions[0].approvals;
    record.structured_fields = revisions.items[0].fields;
    record.proposed_revision = revisions.items[1];
    revisions.submissions = [revisions.submissions[0]];
  }
  if (kind === "service") {
    record.type = "service"; record.title = "Air conditioning in the east meeting room"; record.raw_text = "The east meeting room is becoming too warm during afternoon customer calls. Please inspect the unit and confirm the repair.";
    record.status = "RESOLVED"; record.version = 9; record.structured_fields = null; record.approvals = []; record.current_submission_sequence = null; record.service_cycle_sequence = 6; record.assigned_to = manager;
    record.status_history = [event(1, "created", null, "SUBMITTED"), event(2, "triage", "SUBMITTED", "TRIAGED", manager), event(3, "assign", "TRIAGED", "ASSIGNED", manager), event(4, "start", "ASSIGNED", "IN_PROGRESS", manager), event(5, "resolve", "IN_PROGRESS", "RESOLVED", manager, "Replaced the filter and tested the unit."), event(6, "reopen", "RESOLVED", "REOPENED", id(1), "The room is still warm after lunch. Please check the cooling circuit."), event(7, "start", "REOPENED", "IN_PROGRESS", manager), event(8, "resolve", "IN_PROGRESS", "RESOLVED", manager, "Repaired the coolant connection and verified cooling under load.")]; record.version = 8;
    lifecycle.resolutions = [5, 8].map(sequence => ({ id: id(800 + sequence), cycle_sequence: sequence === 5 ? 4 : 6, event_sequence: sequence, actor_id: manager, at: at(sequence), body: record.status_history.find(item => item.sequence === sequence)!.reason, captured_by: null, captured_at: null }));
    record.current_resolution = lifecycle.resolutions[1]; record.resolution = record.current_resolution.body;
    lifecycle.reopenings = [{ id: id(900), resolution_id: id(805), event_sequence: 6, policy_id: id(901), expires_at: "2026-10-21T14:00:00Z" }];
    revisions.items = []; revisions.submissions = []; revisions.change_requests = [];
  }
  if (kind === "long") {
    record.title = "Replacement workstations for the customer support team across the new floor, including accessibility equipment and coordinated delivery for several start dates";
    record.raw_text = record.raw_text + "\n" + "This is a synthetic long-form intake note used to verify wrapping, reading order, and accessibility. ".repeat(12);
    record.status_history[4].reason = "Please confirm the warranty and vendor details.\n" + "The explanation must remain readable and be preserved exactly, including multiple lines and a reference such as VERY-LONG-SYNTHETIC-REFERENCE-" + "X".repeat(120);
  }
  return { record, revisions, lifecycle };
}
