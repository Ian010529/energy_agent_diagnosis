import { NextRequest } from "next/server";
import { backendHeaders, backendUnavailableResponse, backendUrl } from "@/lib/api/server-client";

export async function GET(_: NextRequest, context: { params: Promise<{ kind: string }> }) {
  const { kind } = await context.params;
  if (!new Set(["live", "ready"]).has(kind)) return Response.json({ error: "not_found" }, { status: 404 });
  let response: Response;
  try {
    response = await fetch(backendUrl(`/health/${kind}`), { headers: await backendHeaders(), cache: "no-store" });
  } catch {
    return backendUnavailableResponse();
  }
  return new Response(response.body, { status: response.status, headers: { "Content-Type": "application/json" } });
}
