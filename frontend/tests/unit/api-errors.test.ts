import { describe, expect, it } from "vitest";
import { ApiError, errorMessage } from "@/lib/api/browser-client";

describe("API error mapping", () => {
  it("distinguishes rate limiting, pilot fail-closed, and backend readiness", () => {
    expect(errorMessage(new ApiError("limited", 429, "RATE_LIMITED", 7))).toContain("7 秒");
    expect(errorMessage(new ApiError("down", 503, "RATE_LIMIT_UNAVAILABLE", null))).toContain("安全关闭");
    expect(errorMessage(new ApiError("down", 503, "DEPENDENCY_UNAVAILABLE", null))).toContain("尚未就绪");
  });

  it("maps authentication and authorization separately", () => {
    expect(errorMessage(new ApiError("no", 401, "AUTHENTICATION_FAILED", null))).toContain("身份验证");
    expect(errorMessage(new ApiError("no", 403, "ROLE_FORBIDDEN", null))).toContain("无权");
  });
});
