import { NextRequest, NextResponse } from "next/server";

const protectedPaths = ["/diagnosis", "/reviews", "/cases", "/system", "/account", "/users"];

export async function middleware(request: NextRequest) {
  if ((process.env.FRONTEND_AUTH_MODE ?? "development_headers") !== "jwt") return NextResponse.next();
  const pathname = request.nextUrl.pathname;
  const access = request.cookies.get("energy_access_token")?.value;
  const needsAuth = protectedPaths.some((path) => pathname === path || pathname.startsWith(`${path}/`));
  if (!access) {
    if (!needsAuth) return NextResponse.next();
    const login = new URL("/login", request.url);
    login.searchParams.set("next", `${pathname}${request.nextUrl.search}`);
    return NextResponse.redirect(login);
  }
  let user: { role: string; must_change_password: boolean } | null = null;
  try {
    const response = await fetch(new URL("/api/v1/auth/me", process.env.BACKEND_BASE_URL ?? "http://127.0.0.1:8000"), {
      headers: {
        Authorization: `Bearer ${access}`,
        "X-Internal-API-Key": process.env.BACKEND_INTERNAL_API_KEY ?? "",
      },
      cache: "no-store",
    });
    if (response.ok) user = await response.json();
  } catch {}
  if (!user) {
    if (pathname === "/login") return NextResponse.next();
    const login = new URL("/login", request.url);
    login.searchParams.set("next", `${pathname}${request.nextUrl.search}`);
    return NextResponse.redirect(login);
  }
  if (user.must_change_password && pathname !== "/account/change-password") {
    return NextResponse.redirect(new URL("/account/change-password", request.url));
  }
  if (pathname === "/login") return NextResponse.redirect(new URL("/diagnosis", request.url));
  if (pathname.startsWith("/users") && user.role !== "admin") {
    return NextResponse.redirect(new URL("/diagnosis", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/login", "/diagnosis/:path*", "/reviews/:path*", "/cases/:path*", "/system/:path*", "/account/:path*", "/users/:path*"],
};
