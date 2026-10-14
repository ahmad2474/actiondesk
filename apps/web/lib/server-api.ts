import "server-only";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";
import type { Auth } from "./api-types";
import { sessionCookies, upstream } from "./transport";
export class ApiError extends Error {
  constructor(public status: number, public requestId?: string) { super("API request failed"); }
}
export async function readApi<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${upstream()}/${path}`, {
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
