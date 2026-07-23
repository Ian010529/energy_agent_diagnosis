import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "@/app/api/backend/[...path]/route";

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
});
