import { NextResponse } from "next/server";
import { backendHeaders, backendUnavailableResponse, backendUrl } from "@/lib/api/server-client";

export async function GET() {
  try {
    const response = await fetch(backendUrl("/api/v1/auth/me"), {
      headers: await backendHeaders(), cache: "no-store",
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return backendUnavailableResponse();
  }
}
