"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { Home, Files, ListChecks, Wrench, Wallet, Plus, Menu, X, ChevronDown, LogOut, ArrowLeft, UserRound } from "lucide-react";
import type { User } from "@/lib/api-types";
import { signOut } from "./session";
const destinations = [
  { title: "Home", href: "/", screen: "home", icon: Home },
  { title: "My Requests", href: "/requests", screen: "requests", icon: Files },
  { title: "Approvals", href: "/approvals", screen: "approvals", icon: ListChecks, roles: ["manager", "finance"] },
  { title: "Service Work", href: "/service-work", screen: "service", icon: Wrench },
  { title: "Finance Processing", href: "/finance-processing", screen: "finance", icon: Wallet, roles: ["finance"] },
];
export function Wordmark() { return <span className="wordmark"><span className="brand-mark" aria-hidden="true"><span /><span /><span /></span>ActionDesk<span className="wordmark-dot" aria-hidden="true">.</span></span>; }
export function AppShell({ user, children, preview = false, screen = "home" }: { user: User; children: React.ReactNode; preview?: boolean; screen?: string }) {
  const pathname = usePathname();
  const [mobile, setMobile] = useState(false);
  const [logoutError, setLogoutError] = useState(false);
  const [pending, setPending] = useState(false);
  const items = destinations.filter(item => !item.roles || item.roles.some(role => user.roles.includes(role as User["roles"][number])));
  const nav = <nav aria-label="Primary navigation">{items.map(item => {
    const current = preview ? item.screen === screen : item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
    const Icon = item.icon;
    return <Link key={item.href} href={preview ? `/preview?screen=${item.screen}` : item.href} className={`nav-link ${current ? "nav-current" : ""}`} aria-current={current ? "page" : undefined} onClick={() => setMobile(false)}><Icon size={19} aria-hidden="true" />{item.title}</Link>;
  })}</nav>;
  async function logout() {
    setPending(true); setLogoutError(false);
    try { if (!await signOut()) { setLogoutError(true); setPending(false); } }
    catch { setLogoutError(true); setPending(false); }
  }
  return <div className={`app-shell ${preview ? "is-preview" : ""}`}>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar"><Link href={preview ? "/preview" : "/"} className="brand-link" aria-label="ActionDesk home"><Wordmark /></Link><p className="nav-label">WORKSPACE</p>{nav}<div className="sidebar-bottom"><p>From requests<br /><strong>to results.</strong></p><span className="caption">{preview ? "Synthetic design preview" : "Your operations workspace"}</span></div></aside>
    <div className="workspace"><header className="app-header"><div className="header-context">
      <Dialog.Root open={mobile} onOpenChange={setMobile}><Dialog.Trigger className="icon-button mobile-menu" aria-label="Open navigation"><Menu size={21} aria-hidden="true" /></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="navigation-drawer"><Dialog.Title><Wordmark /></Dialog.Title><Dialog.Description className="sr-only">Navigate your ActionDesk workspace.</Dialog.Description><Dialog.Close className="icon-button drawer-close" aria-label="Close navigation"><X size={20} /></Dialog.Close>{nav}</Dialog.Content></Dialog.Portal></Dialog.Root>
      <span className="header-label">{preview ? "DESIGN PREVIEW" : "YOUR WORKSPACE"}</span></div><div className="header-actions"><Link className="button button-primary new-request" href={preview ? "/preview?screen=create" : "/requests/new"}><Plus size={17} aria-hidden="true" /><span>New request</span></Link>
      <Dropdown.Root><Dropdown.Trigger className="account-trigger" aria-label="Account menu"><span className="avatar" aria-hidden="true">{user.name.slice(0, 1)}</span><span className="account-name">{user.name}</span><ChevronDown size={15} aria-hidden="true" /></Dropdown.Trigger><Dropdown.Portal><Dropdown.Content className="dropdown" align="end" sideOffset={8}><div className="account-details"><strong>{user.name}</strong><span>{user.email}</span><span className="role-list">{user.roles.join(" · ")}</span></div><Dropdown.Separator className="dropdown-separator" /><Dropdown.Item className="dropdown-item" onSelect={preview ? undefined : () => void logout()} disabled={pending || preview}><LogOut size={16} aria-hidden="true" />{preview ? "Preview account" : pending ? "Signing out…" : "Sign out"}</Dropdown.Item></Dropdown.Content></Dropdown.Portal></Dropdown.Root>
    </div></header>{preview && <div className="preview-banner"><strong>Synthetic preview</strong><span>Fictional examples. No workflow actions are sent to the API.</span><Link href="/login"><ArrowLeft size={14} aria-hidden="true" />Back to live sign in</Link></div>}{logoutError && <div className="connection-banner" role="alert">Could not sign out. Your session may still be active. <button onClick={() => void logout()} disabled={pending}>Try sign out again</button></div>}
    <main id="main-content" tabIndex={-1} className="page-content">{children}</main><footer className="app-footer"><span>ActionDesk</span><span><UserRound size={13} aria-hidden="true" />{preview ? "Synthetic data only" : "Read-only workspace · Workflow actions are not enabled in this release"}</span></footer></div>
  </div>;
}
