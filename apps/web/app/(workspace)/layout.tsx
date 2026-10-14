import { AppShell } from "@/components/shell";
import { SessionBoundary } from "@/components/session";
import { ErrorState } from "@/components/ui";
import { ApiError, currentAuth } from "@/lib/server-api";
export const dynamic = "force-dynamic";
export default async function Workspace({ children }: { children: React.ReactNode }) {
  let auth;
  try { auth = await currentAuth(); }
  catch (error) { if (error instanceof ApiError) return <main className="standalone-error"><ErrorState status={error.status} requestId={error.requestId} /></main>; throw error; }
  return <SessionBoundary user={auth.user}><AppShell user={auth.user}>{children}</AppShell></SessionBoundary>;
}
