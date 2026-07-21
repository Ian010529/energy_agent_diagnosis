import { randomUUID } from "node:crypto";
import { cookies } from "next/headers";

export async function backendHeaders(): Promise<Headers> {
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
  const requestId = randomUUID();
  const headers = new Headers({
    "X-Actor-ID": actorId,
    "X-Actor-Role": role,
    "X-Request-ID": requestId,
    "X-Trace-ID": requestId,
  });
  const key = process.env.BACKEND_INTERNAL_API_KEY;
  if (key) headers.set("X-Internal-API-Key", key);
  return headers;
}

export function backendUrl(path: string): URL {
  const base = process.env.BACKEND_BASE_URL ?? "http://127.0.0.1:8000";
  return new URL(path.replace(/^\//, ""), `${base.replace(/\/$/, "")}/`);
}
