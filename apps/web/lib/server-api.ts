import "server-only";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";
import type { Auth } from "./api-types";
import { readTarget, sessionCookies } from "./transport";
import { ApiError } from "./read-models";
export { ApiError } from "./read-models";
export async function readApi<T>(path: string): Promise<T> {
  const source = new URL(path, "http://read.invalid/");
  if (source.origin !== "http://read.invalid" || path.startsWith("/") || source.hash) throw new Error("Invalid read path");
  const target = readTarget(source.pathname.slice(1), source.searchParams);
  let response: Response;
  try {
    response = await fetch(target, {
      headers: { Cookie: sessionCookies((await headers()).get("cookie") ?? ""), Accept: "application/json" },
      cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(10000),
    });
  } catch { throw new ApiError(0); }
  if (!response.ok) throw new ApiError(response.status, response.headers.get("x-request-id") ?? undefined);
  return response.json() as Promise<T>;
}
export const currentAuth = cache(async (): Promise<Auth> => {
  try { return await readApi<Auth>("auth/me"); }
  catch (error) { if (error instanceof ApiError && error.status === 401) redirect("/login?reason=expired"); throw error; }
});
