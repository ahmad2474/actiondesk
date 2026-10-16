export const metadata = { title: "Finance Processing · ActionDesk" };
import { WorkQueueSection } from "@/components/work-queue";
import { Notice, PageHeader } from "@/components/ui";
import { pageOffset } from "@/lib/read-models";
export default async function Page({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  return <><PageHeader eyebrow="FINANCE OPERATIONS" title="Finance Processing" description="Expense processing is separate from approval decisions." /><Notice>Available and held work comes from the server. No processing can be submitted in this release.</Notice><WorkQueueSection kind="finance_processing" title="Finance processing queue" offset={pageOffset((await searchParams).offset)} href="/finance-processing?offset=" /></>;
}
