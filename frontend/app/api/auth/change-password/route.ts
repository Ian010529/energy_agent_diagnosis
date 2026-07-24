import { NextRequest, NextResponse } from "next/server";
import { backendHeaders, backendUnavailableResponse, backendUrl, sameOrigin } from "@/lib/api/server-client";
import { setAuthCookies } from "@/lib/auth/server";

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json(
    { error: { code: "CSRF_REJECTED" } },
    { status: 403, headers: { "Cache-Control": "no-store" } },
  );
  let response: Response;
  try {
    const headers = await backendHeaders();
    headers.set("Content-Type", "application/json");
    response = await fetch(backendUrl("/api/v1/auth/change-password"), {
      method: "POST", headers, body: await request.arrayBuffer(), cache: "no-store",
    });
  } catch {
    return backendUnavailableResponse();
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) return NextResponse.json(
    payload,
    { status: response.status, headers: { "Cache-Control": "no-store" } },
  );
  const outgoing = NextResponse.json(payload.user, { headers: { "Cache-Control": "no-store" } });
  setAuthCookies(outgoing, payload);
  return outgoing;
}
