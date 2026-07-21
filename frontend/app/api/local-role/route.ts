import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  if ((process.env.FRONTEND_APP_ENV ?? "local") !== "local") {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }
  const body = (await request.json()) as { role?: string };
  if (!body.role || !new Set(["viewer", "operator", "reviewer", "admin"]).has(body.role)) {
    return NextResponse.json({ error: "invalid_role" }, { status: 400 });
  }
  const response = NextResponse.json({ role: body.role });
  response.cookies.set("energy-role", body.role, { sameSite: "strict", httpOnly: true, path: "/" });
  return response;
}
