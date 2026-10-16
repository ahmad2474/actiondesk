export const metadata = { title: "My Requests · ActionDesk" };
import Link from "next/link";
import { redirect } from "next/navigation";
import { PageHeader, ErrorState } from "@/components/ui";
import { RequestList } from "@/components/request-list";
import { ApiError, currentAuth, readApi } from "@/lib/server-api";
import { readOwnedCapabilities } from "@/lib/read-models";
import type { Capabilities, RequestPage } from "@/lib/api-types";
export default async function Requests({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const input = (await searchParams).offset;
  const offset = input && /^\d+$/.test(input) && Number(input) <= 1000000 ? Number(input) : 0;
  let page: RequestPage;
  let capabilities: Record<string, Capabilities | null>;
  const { user } = await currentAuth();
  try {
    page = await readApi<RequestPage>(`requests?scope=mine&limit=20&offset=${offset}`);
    if (page.items.some(record => record.organization_id !== user.organization_id || record.created_by !== user.id)) throw new ApiError(404);
    capabilities = await readOwnedCapabilities(readApi, page.items);
  }
  catch (error) { if (error instanceof ApiError) { if (error.status === 401) redirect("/login?reason=expired"); return <ErrorState status={error.status} requestId={error.requestId} />; } throw error; }
  return <><PageHeader eyebrow="OWNED BY YOU" title="My Requests" description="Your service requests, expenses, and leave. Newest requests first." /><div className="panel panel-flush"><RequestList records={page.items} capabilities={capabilities} /><div className="pagination"><span>{page.items.length ? `Showing ${offset + 1}–${offset + page.items.length}` : "No requests on this page"}</span><nav aria-label="Request pagination">{offset > 0 && <Link className="button button-secondary" href={`/requests?offset=${Math.max(0, offset - 20)}`}>Previous</Link>}{page.items.length === 20 && <Link className="button button-secondary" href={`/requests?offset=${offset + 20}`}>Next</Link>}</nav></div></div></>;
}
