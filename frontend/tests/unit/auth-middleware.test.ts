import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "@/middleware";

const originalAuthMode = process.env.FRONTEND_AUTH_MODE;

afterEach(() => {
  process.env.FRONTEND_AUTH_MODE = originalAuthMode;
  vi.unstubAllGlobals();
});

describe("JWT route protection", () => {
  it("allows the login page to recover an invalid access cookie without redirecting to itself", async () => {
    process.env.FRONTEND_AUTH_MODE = "jwt";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
    const request = new NextRequest("http://localhost/login", {
      headers: { cookie: "energy_access_token=invalid" },
    });

    const response = await middleware(request);

    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(response.headers.get("location")).toBeNull();
  });

  it("preserves the protected destination when authentication must recover on login", async () => {
    process.env.FRONTEND_AUTH_MODE = "jwt";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
    const request = new NextRequest("http://localhost/cases?status=DRAFT", {
      headers: { cookie: "energy_access_token=invalid" },
    });

    const response = await middleware(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost/login?next=%2Fcases%3Fstatus%3DDRAFT",
    );
  });
});
