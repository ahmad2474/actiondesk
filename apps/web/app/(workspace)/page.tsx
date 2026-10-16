export const metadata = { title: "Home · ActionDesk" };
import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight, ListChecks, Wrench, Wallet, Plus } from "lucide-react";
import { PageHeader, ErrorState } from "@/components/ui";
import { RequestList } from "@/components/request-list";
import { ApiError, currentAuth, readApi } from "@/lib/server-api";
import type { RequestPage } from "@/lib/api-types";
export default async function Home() {
  const { user } = await currentAuth();
  let page: RequestPage;
  try { page = await readApi<RequestPage>("requests?scope=mine&limit=5&offset=0"); }
  catch (error) { if (error instanceof ApiError && error.status === 401) redirect("/login?reason=expired"); if (error instanceof ApiError) return <ErrorState status={error.status} requestId={error.requestId} />; throw error; }
  return <><PageHeader eyebrow="YOUR WORK, IN ONE PLACE" title={`Welcome back, ${user.name.split(" ")[0]}.`} description="A clear view of your requests, and where to go next." /><section className="home-intro"><div><p className="eyebrow">START SOMETHING</p><h2>One place for your next request.</h2><p>Service support, expenses, and leave. Follow each request from intake to its recorded outcome.</p></div><Link href="/requests/new" className="button button-primary"><Plus size={17} aria-hidden="true" />New request</Link></section><div className="section-heading home-section"><h2>Recent requests</h2><Link className="text-link" href="/requests">View my requests<ArrowRight size={16} /></Link></div><div className="panel panel-flush"><RequestList records={page.items} /></div><section className="workspace-links"><h2>Your workspace</h2><div className="shortcut-grid">{(user.roles.includes("manager") || user.roles.includes("finance")) && <Link href="/approvals"><ListChecks size={21} aria-hidden="true" /><strong>Approvals</strong><span>Approval decisions and reversal reviews</span><ArrowRight size={17} /></Link>}<Link href="/service-work"><Wrench size={21} aria-hidden="true" /><strong>Service Work</strong><span>Assigned work and department triage</span><ArrowRight size={17} /></Link>{user.roles.includes("finance") && <Link href="/finance-processing"><Wallet size={21} aria-hidden="true" /><strong>Finance Processing</strong><span>Available and held expenses</span><ArrowRight size={17} /></Link>}</div></section></>;
}
