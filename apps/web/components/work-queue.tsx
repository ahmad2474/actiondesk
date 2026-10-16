import Link from "next/link";
import { redirect } from "next/navigation";
import type { QueueKind, WorkQueue } from "@/lib/api-types";
import { ApiError, readApi } from "@/lib/server-api";
import { timestamp, money, dateOnly } from "@/lib/display";
import { ActionAvailability } from "./workflow-availability";
import { EmptyState, ErrorState, StatusBadge } from "./ui";

export async function WorkQueueSection({ kind, title, offset, href }: { kind: QueueKind; title: string; offset: number; href: string }) {
  let queue: WorkQueue;
  try {
    queue = await readApi<WorkQueue>(`work-queues/${kind}?limit=20&offset=${offset}`);
    if (queue.queue !== kind) throw new ApiError(409);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/login?reason=expired");
      return <section aria-label={title}><h2>{title}</h2><ErrorState status={error.status} requestId={error.requestId} /></section>;
    }
    throw error;
  }
  return <section className="live-queue" aria-label={title}><div className="section-heading"><h2>{title}</h2><span className="small-label">Read-only</span></div>
    <p className="caption">Oldest requests first · {queue.organization_timezone}. Actions reflect the server’s latest evaluation; open a request to refresh its detail.</p>
    <div className="panel panel-flush">{!queue.items.length ? <EmptyState title="No work on this page" description="No requests are currently returned for this queue. Refresh to check for changes." /> : queue.items.map(item => <article className="queue-card live-queue-card" key={item.id}>
      <div className="queue-content"><div className="queue-meta"><span className="type-label">{item.type}</span><StatusBadge status={item.status} /></div><h3><Link href={`/requests/${item.id}`}>{item.title}</Link></h3>
        <p className="caption">{item.requester.name} · {item.department.name}{item.assigned_to && <> · Assigned to {item.assigned_to.name}</>}</p>
        {item.amount != null && <p className="queue-money">{item.currency === "PKR" ? money(item.amount) : "Amount unavailable"}</p>}
        {item.start_date && item.end_date && <p>{dateOnly(item.start_date)} – {dateOnly(item.end_date)}</p>}
        <p className="caption">Created <time dateTime={item.created_at}>{timestamp(item.created_at)}</time>{item.due_at && <> · Due <time dateTime={item.due_at}>{timestamp(item.due_at)}</time></>}</p>
        <ActionAvailability actions={item.available_actions} blocking={item.blocking} compact />
      </div><Link className="button button-secondary" href={`/requests/${item.id}`}>View request</Link>
    </article>)}</div>
    <nav className="pagination" aria-label={`${title} pagination`}><span>{queue.items.length ? `Showing ${offset + 1}–${offset + queue.items.length}` : "No requests on this page"}</span><div className="button-group">{offset > 0 && <Link className="button button-secondary" href={`${href}${Math.max(0, offset - queue.limit)}`}>Previous</Link>}{queue.has_more && <Link className="button button-secondary" href={`${href}${offset + queue.limit}`}>Next</Link>}<a className="button button-secondary" href="">Refresh queues</a></div></nav>
  </section>;
}
