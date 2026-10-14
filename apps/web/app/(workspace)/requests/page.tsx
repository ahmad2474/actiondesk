export const metadata = { title: "My Requests · ActionDesk" };
import Link from "next/link";
import { redirect } from "next/navigation";
import { PageHeader, ErrorState } from "@/components/ui";
import { RequestList } from "@/components/request-list";
import { ApiError, readApi } from "@/lib/server-api";
import type { RequestPage } from "@/lib/api-types";
export default async function Requests({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  const input = (await searchParams).offset;
  const offset = input && /^\d+$/.test(input) && Number(input) <= 1000000 ? Number(input) : 0;
  let page: RequestPage;
  try { page = await readApi<RequestPage>(`requests?scope=mine&limit=20&offset=${offset}`); }
  catch (error) { if (error instanceof ApiError) { if (error.status === 401) redirect("/login?reason=expired"); return <ErrorState status={error.status} requestId={error.requestId} />; } throw error; }
  return <><PageHeader eyebrow="OWNED BY YOU" title="My Requests" description="Your service requests, expenses, and leave. Newest requests first." /><div className="panel panel-flush"><RequestList records={page.items} /><div className="pagination"><span>{page.items.length ? `Showing ${offset + 1}–${offset + page.items.length}` : "No requests on this page"}</span><nav aria-label="Request pagination">{offset > 0 && <Link className="button button-secondary" href={`/requests?offset=${Math.max(0, offset - 20)}`}>Previous</Link>}{page.items.length === 20 && <Link className="button button-secondary" href={`/requests?offset=${offset + 20}`}>Next</Link>}</nav></div></div></>;
}
