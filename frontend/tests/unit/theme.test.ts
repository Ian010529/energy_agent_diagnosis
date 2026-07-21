import { describe, expect, it } from "vitest";
import { nextTheme, resolvedTheme } from "@/lib/theme";

describe("theme preference", () => {
  it("cycles through system, light, and dark", () => {
    expect(nextTheme("system")).toBe("light");
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("system");
  });

  it("resolves system without changing the stored preference", () => {
    expect(resolvedTheme("system", true)).toBe("dark");
    expect(resolvedTheme("system", false)).toBe("light");
  });
});
