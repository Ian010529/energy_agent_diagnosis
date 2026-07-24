import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { backendHeaders, backendUrl, sameOrigin } from "@/lib/api/server-client";
import { clearAuthCookies, REFRESH_COOKIE, setAuthCookies } from "@/lib/auth/server";

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json(
    { error: { code: "CSRF_REJECTED" } },
    { status: 403, headers: { "Cache-Control": "no-store" } },
  );
  const refreshToken = (await cookies()).get(REFRESH_COOKIE)?.value;
  if (!refreshToken) return NextResponse.json(
    { error: { code: "AUTH_REFRESH_INVALID" } },
    { status: 401, headers: { "Cache-Control": "no-store" } },
  );
  let backend: Response;
  try {
    const headers = await backendHeaders();
    headers.set("Content-Type", "application/json");
    const clientNetwork = request.headers.get("x-forwarded-for")
      ?? request.headers.get("x-real-ip")
      ?? "bff";
    headers.set("X-Forwarded-For", clientNetwork.split(",", 1)[0].trim());
    backend = await fetch(backendUrl("/api/v1/auth/refresh"), {
      method: "POST", headers, body: JSON.stringify({ refresh_token: refreshToken }), cache: "no-store",
    });
  } catch {
    backend = new Response(null, { status: 503 });
  }
  const payload = await backend.json().catch(() => ({}));
  const outgoing = NextResponse.json(backend.ok ? payload.user : payload, {
    status: backend.status, headers: { "Cache-Control": "no-store" },
  });
  if (backend.ok) setAuthCookies(outgoing, payload); else clearAuthCookies(outgoing);
  return outgoing;
}
