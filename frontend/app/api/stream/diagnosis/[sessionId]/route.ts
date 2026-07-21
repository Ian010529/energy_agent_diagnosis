import { NextRequest } from "next/server";
import { backendHeaders, backendUrl } from "@/lib/api/server-client";

export async function POST(request: NextRequest, context: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await context.params;
  const controller = new AbortController();
  request.signal.addEventListener("abort", () => controller.abort(), { once: true });
  const headers = await backendHeaders();
  headers.set("Content-Type", "application/json");
  const response = await fetch(
    backendUrl(`/api/v1/diagnosis/sessions/${encodeURIComponent(sessionId)}/messages/stream`),
    { method: "POST", headers, body: await request.arrayBuffer(), signal: controller.signal }
  );
  const outgoing = new Headers({ "Cache-Control": "no-cache, no-transform" });
  outgoing.set("Content-Type", response.headers.get("content-type") ?? "text/event-stream; charset=utf-8");
  const retryAfter = response.headers.get("retry-after");
  if (retryAfter) outgoing.set("Retry-After", retryAfter);
  return new Response(response.body, { status: response.status, headers: outgoing });
}
