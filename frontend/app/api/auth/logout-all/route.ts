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
  try {
    const backend = await fetch(backendUrl("/api/v1/auth/logout-all"), {
      method: "POST", headers: await backendHeaders(), cache: "no-store",
    });
    const refreshToken = (await cookies()).get(REFRESH_COOKIE)?.value;
    if (backend.status === 401 && refreshToken) {
      const refreshed = await refreshBackendAuthentication(refreshToken);
      if (refreshed) {
        await fetch(backendUrl("/api/v1/auth/logout-all"), {
          method: "POST", headers: refreshed.headers, cache: "no-store",
        });
      }
    }
  } catch {}
  const outgoing = new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });
  clearAuthCookies(outgoing);
  return outgoing;
}
