import { randomUUID } from "node:crypto";
import { cookies } from "next/headers";

export async function frontendActor(): Promise<{ actorId: string; role: string; local: boolean }> {
  const appEnv = process.env.FRONTEND_APP_ENV ?? "local";
  const cookieStore = await cookies();
  const localRole = appEnv === "local" ? cookieStore.get("energy-role")?.value : undefined;
  const allowed = new Set(["viewer", "operator", "reviewer", "admin"]);
  const role = localRole && allowed.has(localRole)
    ? localRole
    : (process.env.FRONTEND_DEFAULT_ACTOR_ROLE ?? "operator");
  const localActors: Record<string, string> = {
    viewer: process.env.FRONTEND_LOCAL_VIEWER_ACTOR_ID ?? "local-viewer",
    operator: process.env.FRONTEND_LOCAL_OPERATOR_ACTOR_ID ?? "local-operator",
    reviewer: process.env.FRONTEND_LOCAL_REVIEWER_ACTOR_ID ?? "local-reviewer",
    admin: process.env.FRONTEND_LOCAL_ADMIN_ACTOR_ID ?? "local-admin",
  };
  const actorId = appEnv === "local"
    ? localActors[role] ?? localActors.operator
    : (process.env.FRONTEND_DEFAULT_ACTOR_ID ?? "frontend-local");
  return { actorId, role, local: appEnv === "local" };
}

export async function backendHeaders(): Promise<Headers> {
  const requestId = randomUUID();
  const headers = new Headers({
    "X-Request-ID": requestId,
    "X-Trace-ID": requestId,
  });
  const authMode = process.env.FRONTEND_AUTH_MODE ?? "development_headers";
  if (authMode === "jwt") {
    const access = (await cookies()).get("energy_access_token")?.value;
    if (access) headers.set("Authorization", `Bearer ${access}`);
  } else {
    const { actorId, role } = await frontendActor();
    headers.set("X-Actor-ID", actorId);
    headers.set("X-Actor-Role", role);
  }
  const key = process.env.BACKEND_INTERNAL_API_KEY;
  if (key) headers.set("X-Internal-API-Key", key);
  return headers;
}

export function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (!origin || !host) return false;
  try {
    const parsed = new URL(origin);
    return parsed.host === host && parsed.protocol === new URL(request.url).protocol;
  } catch {
    return false;
  }
}

export function backendUrl(path: string): URL {
  const base = process.env.BACKEND_BASE_URL ?? "http://127.0.0.1:8000";
  return new URL(path.replace(/^\//, ""), `${base.replace(/\/$/, "")}/`);
}

export async function refreshBackendAuthentication(refreshToken: string): Promise<{
  headers: Headers;
  refreshToken: string;
} | null> {
  const headers = await backendHeaders();
  headers.set("Content-Type", "application/json");
  const response = await fetch(backendUrl("/api/v1/auth/refresh"), {
    method: "POST",
    headers,
    body: JSON.stringify({ refresh_token: refreshToken }),
    cache: "no-store",
  });
  if (!response.ok) return null;
  const payload = await response.json() as Record<string, unknown>;
  if (typeof payload.access_token !== "string" || typeof payload.refresh_token !== "string") {
    return null;
  }
  headers.set("Authorization", `Bearer ${payload.access_token}`);
  return { headers, refreshToken: payload.refresh_token };
}

export function backendUnavailableResponse(): Response {
  return Response.json(
    {
      error: {
        code: "BACKEND_UNAVAILABLE",
        message: "Backend service is unavailable",
        retryable: true,
        details: {},
      },
    },
    {
      status: 503,
      headers: { "Retry-After": "3", "Cache-Control": "no-store" },
    },
  );
}
