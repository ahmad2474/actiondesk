"use client";
export default function ErrorPage({ reset }: { reset: () => void }) { return <section className="error-state" role="alert"><h1>Could not load this view</h1><p>Your request has not been changed. Try loading this page again.</p><button className="button button-primary" onClick={reset}>Try again</button></section>; }
