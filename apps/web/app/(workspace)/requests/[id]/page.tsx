export const metadata = { title: "Request detail · ActionDesk" };
import { redirect } from "next/navigation";
import { RequestDetailView } from "@/components/request-detail";
import { ErrorState, Notice } from "@/components/ui";
import { WorkflowAvailability } from "@/components/workflow-availability";
import { ReadChoices } from "@/components/read-choices";
import { ApiError, currentAuth, readApi } from "@/lib/server-api";
import { pageOffset, readDetailSnapshot, type DetailSnapshot } from "@/lib/read-models";
import type { Revisions, Lifecycle } from "@/lib/api-types";
export default async function Detail({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ evidenceOffset?: string; assigneeOffset?: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/.test(id)) return <ErrorState status={404} />;
  const { user } = await currentAuth();
  const query = await searchParams;
  const offset = pageOffset(query.evidenceOffset), assigneeOffset = pageOffset(query.assigneeOffset);
  let snapshot: DetailSnapshot;
  try { snapshot = await readDetailSnapshot(readApi, id, assigneeOffset); }
  catch (error) { if (error instanceof ApiError) { if (error.status === 401) redirect("/login?reason=expired"); return <ErrorState status={error.status} requestId={error.requestId} />; } throw error; }
  const { record, capabilities, state } = snapshot;
  if (record.organization_id !== user.organization_id) return <ErrorState status={404} />;
  const [revisions, lifecycle] = await Promise.allSettled([
    readApi<Revisions>(`requests/${id}/revisions?limit=20&offset=${offset}`),
    readApi<Lifecycle>(`requests/${id}/lifecycle?limit=20&offset=${offset}`),
  ]);
  for (const result of [revisions, lifecycle]) if (result.status === "rejected" && result.reason instanceof ApiError) {
    if (result.reason.status === 401) redirect("/login?reason=expired");
    if ([403, 404].includes(result.reason.status)) return <ErrorState status={result.reason.status} />;
  }
  const more = (revisions.status === "fulfilled" && [revisions.value.items, revisions.value.submissions, revisions.value.change_requests].some(items => items.length === 20)) || (lifecycle.status === "fulfilled" && [lifecycle.value.resolutions, lifecycle.value.reopenings, lifecycle.value.reversal_requests, lifecycle.value.reversal_decisions].some(items => items.length === 20));
  const ownerName = capabilities?.participants.find(person => person.id === record.created_by)?.name ?? (record.created_by === user.id ? user.name : "Requester");
  return <><RequestDetailView record={record} ownerName={ownerName} capabilities={capabilities} revisions={revisions.status === "fulfilled" ? revisions.value : null} lifecycle={lifecycle.status === "fulfilled" ? lifecycle.value : null} workflowActions={<><WorkflowAvailability capabilities={capabilities} state={state} />{capabilities?.assignee_choices && <ReadChoices choices={capabilities.assignee_choices} label="Eligible assignees" id="service-assignee" pageHref={next => `?evidenceOffset=${offset}&assigneeOffset=${next}`} />}</>} />
    {(revisions.status === "rejected" || lifecycle.status === "rejected") && <Notice tone="warning">Some evidence could not be loaded. The available request record remains read-only. <a href="">Refresh evidence</a></Notice>}
    <div className="evidence-pagination"><Notice>Evidence groups are paged separately from the complete event timeline. Showing evidence offset {offset}; unavailable entries are not reconstructed.</Notice><nav aria-label="Evidence pagination">{offset > 0 && <a className="button button-secondary" href={`?assigneeOffset=${assigneeOffset}&evidenceOffset=${Math.max(0, offset - 20)}#revisions`}>Previous evidence</a>}{more && <a className="button button-secondary" href={`?assigneeOffset=${assigneeOffset}&evidenceOffset=${offset + 20}#revisions`}>More evidence</a>}</nav></div></>;
}
