/** Fixed upstream; never accept a destination or trusted actor from the browser. */
export function upstream(): string {
  const url = new URL(process.env.ACTIONDESK_API_URL ?? "http://127.0.0.1:8000");
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.pathname !== "/" || url.search || url.hash) throw new Error("Invalid API configuration");
  return url.origin;
}
export function allowedRead(path: string): boolean {
  return path === "auth/me" || path === "requests" || /^requests\/[0-9a-f-]{36}(\/(revisions|lifecycle))?$/.test(path);
}
export function sessionCookies(cookie: string): string {
  return cookie.split(";").map(value => value.trim()).filter(value => /^(?:__Host-actiondesk_session|actiondesk_session_local)=/.test(value)).join("; ");
}
