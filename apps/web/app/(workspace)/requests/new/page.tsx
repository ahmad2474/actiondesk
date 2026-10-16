export const metadata = { title: "New request · ActionDesk" };
import { redirect } from "next/navigation";
import { ReadChoices } from "@/components/read-choices";
import { ErrorState, Notice, PageHeader } from "@/components/ui";
import type { CreationOptions } from "@/lib/api-types";
import { ApiError, readApi } from "@/lib/server-api";
import { pageOffset } from "@/lib/read-models";
export default async function Page({ searchParams }: { searchParams: Promise<{ departmentOffset?: string }> }) {
  let options: CreationOptions;
  try { options = await readApi<CreationOptions>(`requests/options?limit=20&offset=${pageOffset((await searchParams).departmentOffset)}`); }
  catch (error) { if (error instanceof ApiError) { if (error.status === 401) redirect("/login?reason=expired"); return <ErrorState status={error.status} requestId={error.requestId} />; } throw error; }
  return <><PageHeader eyebrow="REQUEST OPTIONS" title="New request" description="Request types and department choices available to your account." /><Notice>Options are read-only. Creating and submitting requests are not enabled in this release.</Notice><section className="panel creation-options"><h2>Available request options</h2><label htmlFor="request-type">Request type · read-only</label><select id="request-type" disabled defaultValue=""><option value="">Available types</option>{options.request_types.map(type => <option key={type} value={type}>{type}</option>)}</select>{options.request_types.length ? <ul className="choice-labels" aria-label="Available request types">{options.request_types.map(type => <li key={type}>{type}</li>)}</ul> : <p>No request types are available.</p>}<ReadChoices choices={options.departments} label="Department choices" id="request-department" pageHref={offset => `/requests/new?departmentOffset=${offset}`} /><p className="caption">Organization timezone: {options.organization_timezone}</p></section></>;
}
