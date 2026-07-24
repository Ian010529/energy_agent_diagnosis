import type { NextResponse } from "next/server";

export const ACCESS_COOKIE = "energy_access_token";
export const REFRESH_COOKIE = "energy_refresh_token";

interface BackendTokens {
  access_token: string;
  refresh_token: string;
  access_expires_in: number;
  refresh_expires_in: number;
}

function secureCookie(): boolean {
  return process.env.AUTH_COOKIE_SECURE !== "false";
}

export function setAuthCookies(response: NextResponse, tokens: BackendTokens) {
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, {
    httpOnly: true,
    secure: secureCookie(),
    sameSite: "strict",
    path: "/",
    maxAge: tokens.access_expires_in,
  });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, {
    httpOnly: true,
    secure: secureCookie(),
    sameSite: "strict",
    path: "/api",
    maxAge: tokens.refresh_expires_in,
  });
}

export function clearAuthCookies(response: NextResponse) {
  response.cookies.set(ACCESS_COOKIE, "", {
    httpOnly: true, secure: secureCookie(), sameSite: "strict", path: "/", maxAge: 0,
  });
  response.cookies.set(REFRESH_COOKIE, "", {
    httpOnly: true, secure: secureCookie(), sameSite: "strict", path: "/api", maxAge: 0,
  });
}
