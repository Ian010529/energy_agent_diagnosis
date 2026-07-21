import { NextResponse } from "next/server";
import { cookies } from "next/headers";

export async function GET() {
  const local = (process.env.FRONTEND_APP_ENV ?? "local") === "local";
  const role = local
    ? (await cookies()).get("energy-role")?.value ?? "operator"
    : process.env.FRONTEND_DEFAULT_ACTOR_ROLE ?? "operator";
  return NextResponse.json({
    local,
    role,
    grafana_url: process.env.GRAFANA_URL ?? null,
    langfuse_url: process.env.LANGFUSE_URL ?? null,
  });
}
