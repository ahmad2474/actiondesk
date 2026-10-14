export const metadata = { title: "Request detail · ActionDesk" };
import { redirect } from "next/navigation";
import { RequestDetailView } from "@/components/request-detail";
import { ErrorState, Notice } from "@/components/ui";
import { ApiError, currentAuth, readApi } from "@/lib/server-api";
import type { RequestDetail, Revisions, Lifecycle } from "@/lib/api-types";
export default async function Detail({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ evidenceOffset?: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/.test(id)) return <ErrorState status={404} />;
  const { user } = await currentAuth();
  const input = (await searchParams).evidenceOffset;
  const offset = input && /^\d+$/.test(input) && Number(input) <= 1000000 ? Number(input) : 0;
  let record: RequestDetail;
  try { record = await readApi<RequestDetail>(`requests/${id}`); }
  catch (error) { if (error instanceof ApiError) { if (error.status === 401) redirect("/login?reason=expired"); return <ErrorState status={error.status} requestId={error.requestId} />; } throw error; }
  if (record.created_by !== user.id) return <ErrorState status={404} />;
  const [revisions, lifecycle] = await Promise.allSettled([
    readApi<Revisions>(`requests/${id}/revisions?limit=20&offset=${offset}`),
    readApi<Lifecycle>(`requests/${id}/lifecycle?limit=20&offset=${offset}`),
  ]);
  for (const result of [revisions, lifecycle]) if (result.status === "rejected" && result.reason instanceof ApiError) {
    if (result.reason.status === 401) redirect("/login?reason=expired");
    if ([403, 404].includes(result.reason.status)) return <ErrorState status={result.reason.status} />;
  }
  const more = (revisions.status === "fulfilled" && [revisions.value.items, revisions.value.submissions, revisions.value.change_requests].some(items => items.length === 20)) || (lifecycle.status === "fulfilled" && [lifecycle.value.resolutions, lifecycle.value.reopenings, lifecycle.value.reversal_requests, lifecycle.value.reversal_decisions].some(items => items.length === 20));
  return <><RequestDetailView record={record} ownerName={user.name} revisions={revisions.status === "fulfilled" ? revisions.value : null} lifecycle={lifecycle.status === "fulfilled" ? lifecycle.value : null} />
    <div className="evidence-pagination"><Notice>Evidence groups are paged separately from the complete event timeline. Showing evidence offset {offset}; unavailable entries are not reconstructed.</Notice><nav aria-label="Evidence pagination">{offset > 0 && <a className="button button-secondary" href={`?evidenceOffset=${Math.max(0, offset - 20)}#revisions`}>Previous evidence</a>}{more && <a className="button button-secondary" href={`?evidenceOffset=${offset + 20}#revisions`}>More evidence</a>}</nav></div></>;
}
