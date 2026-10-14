/** Safe native form fallback: never read, echo, forward, or log the request body.
 * No authentication/session effects. A 303 discards the POST on navigation/reload.
 */
export function POST(): Response {
  return new Response(null, {
    status: 303,
    headers: {
      Location: "/login?reason=javascript",
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
