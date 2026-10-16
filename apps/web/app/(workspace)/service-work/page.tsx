export const metadata = { title: "Service Work · ActionDesk" };
import { WorkQueueSection } from "@/components/work-queue";
import { Notice, PageHeader } from "@/components/ui";
import { pageOffset } from "@/lib/read-models";
export default async function Page({ searchParams }: { searchParams: Promise<{ offset?: string }> }) {
  return <><PageHeader eyebrow="SERVICE OPERATIONS" title="Service Work" description="Assigned work and department triage returned for your account." /><Notice>These are current work records. Workflow controls remain read-only.</Notice><WorkQueueSection kind="service_work" title="Service work queue" offset={pageOffset((await searchParams).offset)} href="/service-work?offset=" /></>;
}
