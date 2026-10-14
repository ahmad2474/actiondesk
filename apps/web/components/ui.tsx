import Link from "next/link";
import { ArrowRight, CircleCheck, CircleAlert, Info, ArrowUpRight, FileText } from "lucide-react";
import type { Status } from "@/lib/api-types";
export const statusLabels: Record<Status, string> = {
  DRAFT: "Draft", SUBMITTED: "Submitted", TRIAGED: "Triaged", ASSIGNED: "Assigned", IN_PROGRESS: "In progress", RESOLVED: "Resolved", CLOSED: "Closed", MANAGER_REVIEW: "Manager review", FINANCE_REVIEW: "Finance review", APPROVED: "Approved", COMPLETED: "Completed", NEEDS_INFO: "Changes requested", REJECTED: "Rejected", WITHDRAWN: "Withdrawn", CANCELLED: "Cancelled", REOPENED: "Reopened", REVERSAL_REVIEW: "Reversal review", REVERSED: "Reversed",
};
export function StatusBadge({ status }: { status: Status }) {
  const tone = ["APPROVED", "COMPLETED", "CLOSED", "RESOLVED"].includes(status) ? "success" : ["NEEDS_INFO", "REVERSAL_REVIEW"].includes(status) ? "warning" : status === "REJECTED" ? "danger" : ["WITHDRAWN", "CANCELLED", "REVERSED", "DRAFT"].includes(status) ? "neutral" : "info";
  return <span className={`status status-${tone}`}><span aria-hidden="true" className="status-dot" />{statusLabels[status]}</span>;
}
export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: React.ReactNode }) {
  return <div className="page-header"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{action}</div>;
}
export function Notice({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "warning" | "success" }) {
  const Icon = tone === "warning" ? CircleAlert : tone === "success" ? CircleCheck : Info;
  return <div className={`notice notice-${tone}`}><Icon size={18} aria-hidden="true" /><div>{children}</div></div>;
}
export function EmptyState({ title, description, href, label }: { title: string; description: string; href?: string; label?: string }) {
  return <div className="empty-state"><span className="empty-icon"><FileText size={26} aria-hidden="true" /></span><h2>{title}</h2><p>{description}</p>{href && <Link className="button button-primary" href={href}>{label}<ArrowRight size={16} aria-hidden="true" /></Link>}</div>;
}
export function ErrorState({ status, requestId }: { status: number; requestId?: string }) {
  const descriptions: Record<number, [string, string]> = {
    0: ["Connection unavailable", "Your requests could not be loaded. Check your connection and try again."],
    403: ["Access unavailable", "Your current account cannot access this view. Refresh your session or return home."],
    404: ["Request unavailable", "This request could not be found or is not visible to your account."],
    409: ["The request changed", "Refresh the request to review its current state. No action will be replayed automatically."],
    422: ["Check the request", "Some information could not be accepted. Review the input before trying again."],
  };
  const [title, description] = descriptions[status] ?? descriptions[0];
  return <section className="error-state" role="alert"><CircleAlert size={28} aria-hidden="true" /><h1>{title}</h1><p>{description}</p><div className="button-group"><a className="button button-primary" href="">Try again</a><Link className="button button-secondary" href="/">Return home</Link></div>{requestId && <p className="caption">Support reference: {requestId}</p>}</section>;
}
export function PreviewLink({ screen = "home", children = "Explore a synthetic preview" }: { screen?: string; children?: React.ReactNode }) { return <Link className="text-link" href={`/preview?screen=${screen}`}>{children}<ArrowUpRight size={16} aria-hidden="true" /></Link>; }
export function Skeletons() { return <div aria-busy="true" aria-label="Loading requests"><span className="sr-only">Loading requests</span><div className="skeleton skeleton-heading" /><div className="panel">{Array.from({ length: 5 }, (_, i) => <div key={i} className="skeleton skeleton-row" />)}</div></div>; }
