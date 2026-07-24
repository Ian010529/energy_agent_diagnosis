import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import {
  backendHeaders,
  backendUrl,
  refreshBackendAuthentication,
  sameOrigin,
} from "@/lib/api/server-client";
import { clearAuthCookies, REFRESH_COOKIE } from "@/lib/auth/server";

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json(
    { error: { code: "CSRF_REJECTED" } },
    { status: 403, headers: { "Cache-Control": "no-store" } },
  );
  const token = (await cookies()).get(REFRESH_COOKIE)?.value;
  if (token) {
    try {
      const headers = await backendHeaders();
      headers.set("Content-Type", "application/json");
      const backend = await fetch(backendUrl("/api/v1/auth/logout"), {
        method: "POST", headers, body: JSON.stringify({ refresh_token: token }), cache: "no-store",
      });
      if (backend.status === 401) {
        const refreshed = await refreshBackendAuthentication(token);
        if (refreshed) {
          await fetch(backendUrl("/api/v1/auth/logout"), {
            method: "POST",
            headers: refreshed.headers,
            body: JSON.stringify({ refresh_token: refreshed.refreshToken }),
            cache: "no-store",
          });
        }
      }
    } catch {}
  }
  const outgoing = new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });
  clearAuthCookies(outgoing);
  return outgoing;
}
