"use client";
import { useState, type FormEvent } from "react";
import { Eye, EyeOff, ArrowRight, CircleAlert } from "lucide-react";
export function LoginForm({ expired, unavailable }: { expired: boolean; unavailable: boolean }) {
  const [visible, setVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [retryAt, setRetryAt] = useState(0);
  const [fields, setFields] = useState<{ email?: string; password?: string }>({});
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const email = String(data.get("email") ?? "").trim();
    const password = String(data.get("password") ?? "");
    const invalid = { email: !email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? "Enter your email address." : undefined, password: !password ? "Enter your password." : undefined };
    setFields(invalid); setError("");
    if (invalid.email || invalid.password) { (form.elements.namedItem(invalid.email ? "email" : "password") as HTMLElement)?.focus(); return; }
    if (Date.now() < retryAt) { setError("Please wait before trying again."); return; }
    setPending(true);
    try {
      const response = await fetch("/api/actiondesk/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
      if (response.ok) { form.reset(); window.location.replace("/"); return; }
      const messages: Record<number, string> = { 401: "We couldn’t sign you in. Check your email and password.", 403: "Sign-in security checks failed. Refresh this page and try again.", 422: "Your sign-in details could not be accepted. Check both fields.", 429: "Too many sign-in attempts. Please wait before trying again.", 503: "Sign-in is temporarily unavailable. Please try again later." };
      if (response.status === 429) {
        const value = response.headers.get("retry-after") ?? "60";
        const seconds = /^\d+$/.test(value) ? Number(value) : Math.max(1, (Date.parse(value) - Date.now()) / 1000);
        setRetryAt(Date.now() + (Number.isFinite(seconds) ? seconds : 60) * 1000);
      }
      setError(messages[response.status] ?? "Could not sign in. Please try again.");
    } catch { setError("Connection unavailable. Check your connection and try again."); }
    setPending(false);
  }
  // Native submission must be safe before hydration and when client JS fails.
  // This POST target discards the body; only the hydrated handler authenticates.
  return <form className="login-form" method="post" action="/api/actiondesk/login-unavailable" onSubmit={submit} noValidate aria-busy={pending}>
    <noscript><p className="notice notice-warning">JavaScript is required to sign in. Enable it and reload this page.</p></noscript>
    {unavailable && <div className="notice notice-warning" role="alert">Sign-in did not run. Enable JavaScript and reload this page. If it is already enabled, reload to finish loading sign-in, then try again.</div>}
    {expired && <div className="notice notice-warning" role="status">Your session ended. Sign in again to continue. No action has been replayed.</div>}
    {error && <div className="form-error" role="alert"><CircleAlert size={18} aria-hidden="true" />{error}</div>}
    <div className="form-field"><label htmlFor="email">Email address</label><input id="email" name="email" type="email" autoComplete="username" autoCapitalize="none" spellCheck={false} required aria-invalid={!!fields.email} aria-describedby={fields.email ? "email-error" : undefined} />{fields.email && <p id="email-error" className="field-error">{fields.email}</p>}</div>
    <div className="form-field"><label htmlFor="password">Password</label><div className="password-input"><input id="password" name="password" type={visible ? "text" : "password"} autoComplete="current-password" required aria-invalid={!!fields.password} aria-describedby={fields.password ? "password-error" : undefined} /><button type="button" className="icon-button" aria-label={visible ? "Hide password" : "Show password"} aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={19} /> : <Eye size={19} />}</button></div>{fields.password && <p id="password-error" className="field-error">{fields.password}</p>}</div>
    <button className="button button-primary login-submit" disabled={pending} type="submit">{pending ? "Signing in…" : "Sign in"}<ArrowRight size={17} aria-hidden="true" /></button>
    <p className="caption login-help">Use your organization account. Need access? Contact your organization administrator.</p>
  </form>;
}
