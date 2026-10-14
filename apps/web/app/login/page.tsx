export const metadata = { title: "Sign in · ActionDesk" };
import { LoginForm } from "@/components/login-form";
import { Wordmark } from "@/components/shell";
import { PreviewLink } from "@/components/ui";
export default async function Login({ searchParams }: { searchParams: Promise<{ reason?: string }> }) {
  const { reason } = await searchParams;
  return <main className="login-page"><section className="login-brand"><Wordmark /><div className="login-message"><p className="eyebrow">WORK, WITH A CLEAR NEXT STEP</p><h2>From requests<br />to results.</h2><p>A considered workspace for service requests, expenses, and leave.</p><div className="login-steps"><span>01&nbsp; Request</span><span>02&nbsp; Review</span><span>03&nbsp; Resolve</span></div></div><span className="caption">ActionDesk · Internal operations</span></section><section className="login-card"><div><p className="eyebrow">WELCOME BACK</p><h1>Sign in to ActionDesk</h1><p className="page-description">Keep your work moving forward.</p><LoginForm expired={reason === "expired"} unavailable={reason === "javascript"} /><div className="login-preview"><PreviewLink>View the synthetic design preview</PreviewLink></div></div></section></main>;
}
