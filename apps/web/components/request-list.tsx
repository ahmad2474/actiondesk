import Link from "next/link";
import { ArrowUpRight, Wrench, Wallet, CalendarDays } from "lucide-react";
import type { RequestRecord } from "@/lib/api-types";
import { identifier, timestamp } from "@/lib/display";
import { StatusBadge, EmptyState } from "./ui";
export function RequestList({ records, preview = false }: { records: RequestRecord[]; preview?: boolean }) {
  if (!records.length) return <EmptyState title="Your next request starts here" description="Service requests, expenses, and leave will appear here once they’re created." href="/requests/new" label="Explore request creation" />;
  const href = (id: string) => preview ? "/preview?screen=detail" : `/requests/${id}`;
  const icon = (type: string) => { const Icon = type === "service" ? Wrench : type === "expense" ? Wallet : CalendarDays; return <Icon size={18} aria-hidden="true" />; };
  return <div className="request-list"><table className="request-table"><caption className="sr-only">Requests ordered by newest creation first</caption><thead><tr><th scope="col">Request</th><th scope="col">Type</th><th scope="col">Status</th><th scope="col">Created</th><th scope="col"><span className="sr-only">Open request</span></th></tr></thead><tbody>{records.map(record => <tr key={record.id}><td><Link href={href(record.id)} className="request-title">{record.title}</Link><span className="request-id">{identifier(record.id)}</span></td><td><span className="type-label">{icon(record.type)}{record.type}</span></td><td><StatusBadge status={record.status} /></td><td><time dateTime={record.created_at} className="date-cell">{timestamp(record.created_at)}</time></td><td><Link className="icon-button" href={href(record.id)} aria-label={`Open ${record.title}`}><ArrowUpRight size={18} aria-hidden="true" /></Link></td></tr>)}</tbody></table>
    <ul className="request-cards">{records.map(record => <li key={record.id}><div className="card-top"><span className="type-label">{icon(record.type)}{record.type}</span><StatusBadge status={record.status} /></div><Link href={href(record.id)} className="request-title">{record.title}</Link><div className="card-meta"><span>{identifier(record.id)}</span><time dateTime={record.created_at}>{timestamp(record.created_at)}</time></div></li>)}</ul></div>;
}
