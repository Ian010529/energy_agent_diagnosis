import { NextRequest } from "next/server";
import { backendHeaders, backendUnavailableResponse, backendUrl } from "@/lib/api/server-client";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const target = backendUrl(`/api/v1/${path.join("/")}`);
  target.search = request.nextUrl.search;
  const headers = await backendHeaders();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const idempotency = request.headers.get("idempotency-key");
  if (idempotency) headers.set("Idempotency-Key", idempotency);
  let response: Response;
  try {
    response = await fetch(target, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
      cache: "no-store",
    });
  } catch {
    return backendUnavailableResponse();
  }
  const outgoing = new Headers();
  for (const name of ["content-type", "retry-after", "x-trace-id", "x-request-id"]) {
    const value = response.headers.get(name);
    if (value) outgoing.set(name, value);
  }
  return new Response(response.body, { status: response.status, headers: outgoing });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
