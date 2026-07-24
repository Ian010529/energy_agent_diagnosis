import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "@/app/api/backend/[...path]/route";
import { sameOrigin } from "@/lib/api/server-client";

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("BFF upstream failures", () => {
  it("maps an unreachable FastAPI backend to a retryable JSON 503", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("fetch failed"))));
    const response = await GET(
      new NextRequest("http://localhost/api/backend/capabilities"),
      { params: Promise.resolve({ path: ["capabilities"] }) },
    );

    expect(response.status).toBe(503);
    expect(response.headers.get("content-type")).toContain("application/json");
    expect(response.headers.get("retry-after")).toBe("3");
    expect(await response.json()).toMatchObject({
      error: {
        code: "BACKEND_UNAVAILABLE",
        retryable: true,
      },
    });
  });

  it("rejects a different scheme even when the Origin host matches", () => {
    const request = new Request("https://energy.example/api/backend/users", {
      headers: { host: "energy.example", origin: "http://energy.example" },
    });

    expect(sameOrigin(request)).toBe(false);
  });

  it("marks rejected and successful write responses as no-store", async () => {
    const rejected = await POST(
      new NextRequest("https://energy.example/api/backend/users", {
        method: "POST",
        headers: { host: "energy.example", origin: "http://energy.example" },
      }),
      { params: Promise.resolve({ path: ["users"] }) },
    );
    expect(rejected.status).toBe(403);
    expect(rejected.headers.get("cache-control")).toBe("no-store");

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", {
      status: 201,
      headers: { "Content-Type": "application/json" },
    })));
    const accepted = await POST(
      new NextRequest("https://energy.example/api/backend/users", {
        method: "POST",
        headers: { host: "energy.example", origin: "https://energy.example" },
        body: "{}",
      }),
      { params: Promise.resolve({ path: ["users"] }) },
    );
    expect(accepted.status).toBe(201);
    expect(accepted.headers.get("cache-control")).toBe("no-store");
  });
});
