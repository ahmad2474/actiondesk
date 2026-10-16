import type { ActionCapability, ActionBlock, Capabilities } from "@/lib/api-types";
import { LockKeyhole } from "lucide-react";
import { Notice } from "./ui";

const labels: Partial<Record<ActionCapability["action"], string>> = {
  submit: "Submit request", approve: "Approve", reject: "Reject", request_changes: "Request changes",
  revise: "Revise", resubmit: "Resubmit", triage: "Triage", assign: "Assign", start: "Start work",
  resolve: "Resolve", close: "Close", process: "Process expense", cancel: "Cancel request",
  request_reversal: "Request reversal", approve_reversal: "Accept reversal", reject_reversal: "Deny reversal",
  create_correction: "Create correction draft", reopen: "Reopen service",
};
export function ActionAvailability({ actions, blocking = [], compact = false }: { actions: ActionCapability[]; blocking?: ActionBlock[]; compact?: boolean }) {
  return <div className={`action-availability${compact ? " action-compact" : ""}`}>
    <p className="small-label">Available actions · read-only</p>
    {actions.length ? <div className="button-group">{actions.map(item => labels[item.action] && <button key={item.action} type="button" className="button button-secondary" disabled>{labels[item.action]}</button>)}</div> : <p className="caption">No actions are currently available.</p>}
    {blocking.map(item => <p className="caption" key={item.action}>{item.message}</p>)}
  </div>;
}
export function WorkflowAvailability({ capabilities, state }: { capabilities: Capabilities | null; state: "ready" | "stale" | "unavailable" }) {
  return <><div className="read-only-label"><LockKeyhole size={17} aria-hidden="true" /><strong>Read-only view</strong></div>
    <p>Availability is supplied by the server. Workflow actions are not enabled in this release.</p>
    {capabilities ? <><ActionAvailability actions={capabilities.available_actions} blocking={capabilities.blocking} /><p className="caption">Organization timezone: {capabilities.organization_timezone}</p></> : <Notice tone="warning">{state === "stale" ? "The request changed while loading. Action availability and participant names are withheld." : "Action availability and participant names could not be loaded."} <a href="">Refresh current request</a></Notice>}
  </>;
}
