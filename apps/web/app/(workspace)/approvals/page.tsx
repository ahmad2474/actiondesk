export const metadata = { title: "Approvals · ActionDesk" };
import { Suspense } from "react";
import { WorkQueueSection } from "@/components/work-queue";
import { Notice, PageHeader, Skeletons } from "@/components/ui";
import { pageOffset } from "@/lib/read-models";
export default async function Page({ searchParams }: { searchParams: Promise<{ offset?: string; reversalOffset?: string }> }) {
  const params = await searchParams;
  const offset = pageOffset(params.offset), reversalOffset = pageOffset(params.reversalOffset);
  return <><PageHeader eyebrow="REVIEW WORK" title="Approvals" description="Approval decisions and independent reversal reviews returned for your account." /><Notice>Action availability is live read data. Decisions cannot be submitted in this release.</Notice>
    <Suspense fallback={<Skeletons />}><WorkQueueSection kind="approvals" title="Approval decisions" offset={offset} href={`/approvals?reversalOffset=${reversalOffset}&offset=`} /></Suspense>
    <Suspense fallback={<Skeletons />}><WorkQueueSection kind="reversals" title="Independent reversal reviews" offset={reversalOffset} href={`/approvals?offset=${offset}&reversalOffset=`} /></Suspense></>;
}
