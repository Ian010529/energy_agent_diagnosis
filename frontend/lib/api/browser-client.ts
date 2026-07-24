export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly retryAfter: number | null,
  ) {
    super(message);
  }
}

let refreshFlight: Promise<boolean> | null = null;
type AuthMessage = "auth-refreshed" | "auth-logged-out";
const localListeners = new Set<(message: AuthMessage) => void>();
const channel = typeof window !== "undefined" && "BroadcastChannel" in window
  ? new BroadcastChannel("energy-auth")
  : null;

function publishAuth(message: AuthMessage) {
  for (const listener of localListeners) listener(message);
  channel?.postMessage(message);
}

export async function refreshSession(): Promise<boolean> {
  if (refreshFlight) return refreshFlight;
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), 5_000);
  const refresh = () => fetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    keepalive: true,
    signal: controller.signal,
  }).then((response) => {
    if (response.ok) publishAuth("auth-refreshed");
    return response.ok;
  }).catch(() => false);
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  const refreshWithLock = async (): Promise<boolean> => {
    try {
      if (!locks) return await refresh();
      return await locks.request(
        "energy-auth-refresh",
        { signal: controller.signal },
        refresh,
      );
    } catch {
      return false;
    } finally {
      globalThis.clearTimeout(timeout);
    }
  };
  const flight = refreshWithLock().finally(() => { refreshFlight = null; });
  refreshFlight = flight;
  return flight;
}

export function broadcastLogout() {
  publishAuth("auth-logged-out");
}

export function subscribeAuth(
  listener: (message: AuthMessage) => void,
): () => void {
  localListeners.add(listener);
  const onMessage = (event: MessageEvent) => {
    if (event.data === "auth-refreshed" || event.data === "auth-logged-out") {
      listener(event.data);
    }
  };
  channel?.addEventListener("message", onMessage);
  return () => {
    localListeners.delete(listener);
    channel?.removeEventListener("message", onMessage);
  };
}

export async function api<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const response = await fetch(`/api/backend/${path.replace(/^\//, "")}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as {
      error?: { code?: string; message?: string };
    };
    const code = payload.error?.code ?? "UNKNOWN";
    if (!retried && response.status === 401 && ["AUTH_TOKEN_EXPIRED", "AUTH_TOKEN_INVALID"].includes(code)) {
      if (await refreshSession()) return api<T>(path, init, true);
      broadcastLogout();
      if (typeof window !== "undefined") window.location.assign("/login");
    }
    throw new ApiError(
      payload.error?.message ?? `Request failed (${response.status})`,
      response.status,
      code,
      Number(response.headers.get("retry-after")) || null,
    );
  }
  return response.json() as Promise<T>;
}

export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "无法连接后端，请稍后重试。";
  if (error.status === 401) return "身份验证失败，请联系管理员。";
  if (error.status === 403) return "当前角色无权执行此操作。";
  if (error.status === 429) return `请求过于频繁${error.retryAfter ? `，${error.retryAfter} 秒后重试` : ""}。`;
  if (error.status === 503 && error.code === "RATE_LIMIT_UNAVAILABLE") return "限流服务不可用，试点写入已安全关闭。";
  if (error.status === 503) return "诊断后端尚未就绪或依赖正在降级。";
  return error.message;
}
