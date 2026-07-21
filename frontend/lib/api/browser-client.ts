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

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/${path.replace(/^\//, "")}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as {
      error?: { code?: string; message?: string };
    };
    throw new ApiError(
      payload.error?.message ?? `Request failed (${response.status})`,
      response.status,
      payload.error?.code ?? "UNKNOWN",
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
