import type { components } from "@actiondesk/contracts";
export type Auth = components["schemas"]["AuthRead"];
export type User = Auth["user"];
export type RequestRecord = components["schemas"]["RequestRead"];
export type RequestDetail = components["schemas"]["RequestDetail"];
export type RequestPage = components["schemas"]["RequestPage"];
export type Revisions = components["schemas"]["RevisionPage"];
export type Lifecycle = components["schemas"]["LifecyclePage"];
export type Status = RequestRecord["status"];
