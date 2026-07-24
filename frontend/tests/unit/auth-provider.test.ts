import { afterEach, describe, expect, it, vi } from "vitest";
import {
  broadcastLogout,
  refreshSession,
  subscribeAuth,
} from "@/lib/api/browser-client";
import { currentUser } from "@/lib/auth/provider";

const originalLocks = navigator.locks;

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Object.defineProperty(navigator, "locks", {
    configurable: true,
    value: originalLocks,
  });
});

describe("auth session recovery", () => {
  it("uses a browser-wide lock before rotating a refresh token", async () => {
    const request = vi.fn(async (
      _name: string,
      _options: LockOptions,
      callback: () => Promise<boolean>,
    ) => callback());
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: { request },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));

    await expect(refreshSession()).resolves.toBe(true);

    expect(request).toHaveBeenCalledWith(
      "energy-auth-refresh",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
      expect.any(Function),
    );
  });

  it("rotates the refresh cookie and retries current-user once", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ status: 401, ok: false })
      .mockResolvedValueOnce({ status: 200, ok: true })
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({ user_id: "user-1", role: "operator" }),
      });
    vi.stubGlobal("fetch", fetchMock);

    await expect(currentUser()).resolves.toMatchObject({ user_id: "user-1" });
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/auth/refresh", expect.objectContaining({
      keepalive: true,
      method: "POST",
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/auth/me", { cache: "no-store" });
  });

  it("notifies the current tab as well as other tabs when authentication is lost", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeAuth(listener);

    broadcastLogout();

    expect(listener).toHaveBeenCalledWith("auth-logged-out");
    unsubscribe();
  });

  it("settles as logged out when current-user refresh fails", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ status: 401, ok: false })
      .mockResolvedValueOnce({ status: 401, ok: false });
    vi.stubGlobal("fetch", fetchMock);

    await expect(currentUser()).resolves.toBeNull();

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
