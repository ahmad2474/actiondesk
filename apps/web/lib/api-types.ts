import type { paths } from "@actiondesk/contracts";
export type HealthResponse = paths["/health"]["get"]["responses"][200]["content"]["application/json"];
export type ReadinessResponse = paths["/ready"]["get"]["responses"][200]["content"]["application/json"];
