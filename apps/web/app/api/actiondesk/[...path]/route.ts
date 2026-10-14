import { allowedRead, sessionCookies, upstream } from "@/lib/transport";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };
async function forward(request: Request, context: Context): Promise<Response> {
  const path = (await context.params).path.join("/");
  const mutation = request.method === "POST";
  if (!(mutation ? ["auth/login", "auth/logout"].includes(path) : allowedRead(path))) {
    return Response.json({ title: "Not available", detail: "This interface supports authentication and read-only requests." }, { status: 404, headers: { "Cache-Control": "no-store" } });
  }
  const source = new URL(request.url);
  const target = new URL(`${upstream()}/${path}`);
  // No scopes can expand the owned-request list through this 6A adapter.
  if (path === "requests") target.searchParams.set("scope", "mine");
  for (const name of ["limit", "offset"]) {
    const value = source.searchParams.get(name);
    if (value !== null) target.searchParams.set(name, value);
  }
  const headers = new Headers({ Accept: "application/json" });
  for (const name of ["origin", "content-type", "x-csrf-token"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const cookie = sessionCookies(request.headers.get("cookie") ?? "");
  if (cookie) headers.set("cookie", cookie);
  try {
    const response = await fetch(target, {
      method: request.method, headers, body: mutation ? await request.text() : undefined,
      cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(10000),
    });
    const outgoing = new Headers({ "Cache-Control": "no-store", Vary: "Cookie", "X-Content-Type-Options": "nosniff" });
    for (const name of ["content-type", "x-request-id", "retry-after"]) {
      const value = response.headers.get(name); if (value) outgoing.set(name, value);
    }
    for (const value of response.headers.getSetCookie()) outgoing.append("set-cookie", value);
    return new Response(response.body, { status: response.status, headers: outgoing });
  } catch {
    return Response.json({ title: "Connection unavailable", detail: "Could not reach ActionDesk. Try again when your connection is available." }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
export const GET = forward;
export const POST = forward;
