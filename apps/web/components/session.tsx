"use client";
import { useEffect, useState } from "react";
import type { Auth, User } from "@/lib/api-types";
/** No tokens or sensitive data are persisted. Verify restored pages before showing cached work. */
export function SessionBoundary({ children, user }: { children: React.ReactNode; user: Pick<User, "id" | "organization_id" | "roles"> }) {
  const [state, setState] = useState<"ready" | "checking" | "expired">("ready");
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    let active = true;
    async function verify() {
      try {
        const response = await fetch("/api/actiondesk/auth/me", { cache: "no-store" });
        if (!active) return;
        if (response.status === 401 || response.status === 403) {
          setState("expired"); window.location.replace("/login?reason=expired");
        } else if (response.ok) {
          const current: Auth = await response.json();
          if (!active) return;
          if (current.user.id !== user.id || current.user.organization_id !== user.organization_id || [...current.user.roles].sort().join(",") !== [...user.roles].sort().join(",")) {
            setState("checking"); window.location.replace("/"); return;
          }
          setState("ready"); setOffline(false);
        } else { setState("ready"); setOffline(true); }
      } catch { if (active) { setOffline(true); setState("ready"); } }
    }
    function restored(event: PageTransitionEvent) { if (event.persisted) { setState("checking"); void verify(); } }
    function visibility() { if (document.visibilityState === "visible") { setState("checking"); void verify(); } }
    function connected() { setOffline(false); void verify(); }
    function disconnected() { setOffline(true); }
    window.addEventListener("pageshow", restored);
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("online", connected);
    window.addEventListener("offline", disconnected);
    void verify();
    return () => { active = false; window.removeEventListener("pageshow", restored); document.removeEventListener("visibilitychange", visibility); window.removeEventListener("online", connected); window.removeEventListener("offline", disconnected); };
  }, [user]);
  if (state !== "ready") return <main className="session-check" role="status">{state === "expired" ? "Your session ended. Returning to sign in…" : "Checking your session…"}</main>;
  return <>{offline && <div className="connection-banner" role="status">Connection unavailable. Displayed information may be out of date.</div>}{children}</>;
}
export async function signOut(): Promise<boolean> {
  const context = await fetch("/api/actiondesk/auth/me", { cache: "no-store" });
  if (context.status === 401) { window.location.replace("/login"); return true; }
  if (!context.ok) return false;
  const auth: Auth = await context.json();
  const response = await fetch("/api/actiondesk/auth/logout", { method: "POST", headers: { "X-CSRF-Token": auth.csrf_token } });
  if (!response.ok) return false;
  window.location.replace("/login"); return true;
}
