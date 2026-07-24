import { NextResponse } from "next/server";
import { backendHeaders, backendUrl, frontendActor } from "@/lib/api/server-client";

export async function GET() {
  if ((process.env.FRONTEND_AUTH_MODE ?? "development_headers") === "jwt") {
    try {
      const response = await fetch(backendUrl("/api/v1/auth/me"), { headers: await backendHeaders(), cache: "no-store" });
      const user = response.ok ? await response.json() : null;
      return NextResponse.json({
        auth_mode: "jwt", authenticated: response.ok, user,
        role: user?.role ?? null, actor_id: user?.user_id ?? null,
        grafana_url: process.env.GRAFANA_URL ?? null, langfuse_url: process.env.LANGFUSE_URL ?? null,
      });
    } catch {
      return NextResponse.json({ auth_mode: "jwt", authenticated: false, user: null }, { status: 503 });
    }
  }
  const actor = await frontendActor();
  return NextResponse.json({
    auth_mode: process.env.FRONTEND_AUTH_MODE ?? "development_headers",
    authenticated: true,
    local: actor.local,
    role: actor.role,
    actor_id: actor.actorId,
    grafana_url: process.env.GRAFANA_URL ?? null,
    langfuse_url: process.env.LANGFUSE_URL ?? null,
  });
}
