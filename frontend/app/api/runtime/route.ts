import { NextResponse } from "next/server";
import { frontendActor } from "@/lib/api/server-client";

export async function GET() {
  const actor = await frontendActor();
  return NextResponse.json({
    local: actor.local,
    role: actor.role,
    actor_id: actor.actorId,
    grafana_url: process.env.GRAFANA_URL ?? null,
    langfuse_url: process.env.LANGFUSE_URL ?? null,
  });
}
