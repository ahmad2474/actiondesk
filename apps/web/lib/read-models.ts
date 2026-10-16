import type { Capabilities, RequestDetail, RequestRecord } from "./api-types";

export class ApiError extends Error {
  status: number;
  requestId?: string;
  constructor(status: number, requestId?: string) {
    super("API request failed"); this.status = status; this.requestId = requestId;
  }
}
export type ReadApi = <T>(path: string) => Promise<T>;
export function accessFailure(error: unknown): boolean {
  return error instanceof ApiError && [401, 403, 404].includes(error.status);
}
export function pageOffset(input?: string): number {
  return input && /^\d+$/.test(input) && Number(input) <= 1000000 ? Number(input) : 0;
}
export function matchesRequest(record: Pick<RequestRecord, "id" | "version" | "department_id">, capabilities: Capabilities): boolean {
  return capabilities.request_id === record.id && capabilities.expected_version === record.version && capabilities.department.id === record.department_id;
}
/** Consistency checks bind supplied capabilities; they never grant an action. */
export function matchesDetail(record: RequestDetail, capabilities: Capabilities): boolean {
  if (!matchesRequest(record, capabilities)) return false;
  const actions = capabilities.available_actions;
  if (new Set(actions.map(item => item.action)).size !== actions.length) return false;
  if (capabilities.assignee_choices && !actions.some(item => item.action === "assign")) return false;
  return actions.every(item => {
    if (item.action === "route") return false;
    if (["approve", "reject", "request_changes"].includes(item.action)) {
      const current = [...(record.approvals ?? [])].sort((a, b) => a.step - b.step).find(step => step.status === "pending");
      if (!item.approval_id || item.approval_id !== current?.id) return false;
    } else if (item.approval_id) return false;
    if (item.action === "resubmit") {
      if (!item.revision_id || item.revision_id !== record.proposed_revision?.id) return false;
    } else if (item.revision_id) return false;
    if (["approve_reversal", "reject_reversal", "create_correction"].includes(item.action)) {
      if (!item.reversal_request_id || item.reversal_request_id !== record.active_reversal?.id) return false;
    } else if (item.reversal_request_id) return false;
    if (item.action === "reopen") {
      // Trusted legacy resolutions have no persisted ID until a real mutation.
      if ((item.resolution_id ?? null) !== (record.current_resolution?.id ?? null)) return false;
    } else if (item.resolution_id) return false;
    return true;
  });
}
export type DetailSnapshot = { record: RequestDetail; capabilities: Capabilities | null; state: "ready" | "stale" | "unavailable" };
export async function readDetailSnapshot(read: ReadApi, id: string, offset = 0): Promise<DetailSnapshot> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const [detail, capabilities] = await Promise.allSettled([
      read<RequestDetail>(`requests/${id}`),
      read<Capabilities>(`requests/${id}/capabilities?limit=20&offset=${offset}`),
    ]);
    if (detail.status === "rejected") throw detail.reason;
    if (detail.value.id !== id) throw new ApiError(404);
    if (capabilities.status === "rejected") {
      if (accessFailure(capabilities.reason)) throw capabilities.reason;
      return { record: detail.value, capabilities: null, state: "unavailable" };
    }
    if (matchesDetail(detail.value, capabilities.value)) return { record: detail.value, capabilities: capabilities.value, state: "ready" };
    if (attempt === 1) return { record: detail.value, capabilities: null, state: "stale" };
  }
  throw new Error("Unreachable snapshot state");
}
export async function readOwnedCapabilities(read: ReadApi, records: RequestRecord[]): Promise<Record<string, Capabilities | null>> {
  const results = await Promise.allSettled(records.map(record => read<Capabilities>(`requests/${record.id}/capabilities`)));
  return Object.fromEntries(results.map((result, index) => {
    if (result.status === "rejected" && accessFailure(result.reason)) throw result.reason;
    const record = records[index];
    return [record.id, result.status === "fulfilled" && matchesRequest(record, result.value) ? result.value : null];
  }));
}
