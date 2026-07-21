"use client";

import { AlertTriangle, Inbox } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, errorMessage } from "@/lib/api/browser-client";

export function EmptyState({ title = "暂无内容", detail }: { title?: string; detail?: string }) {
  return <div className="empty"><div><Inbox size={22} aria-hidden /><strong>{title}</strong>{detail ? <span>{detail}</span> : null}</div></div>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="error-state" role="alert"><div><AlertTriangle size={22} aria-hidden /><strong>加载失败</strong><p>{message}</p>{retry ? <button className="button" onClick={retry}>重试</button> : null}</div></div>;
}

export function RequestErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const initial = error instanceof ApiError ? error.retryAfter ?? 0 : 0;
  const [remaining, setRemaining] = useState(initial);
  useEffect(() => {
    if (remaining <= 0) return;
    const timer = window.setInterval(() => setRemaining((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [remaining]);
  const message = error instanceof ApiError && error.status === 429 && remaining > 0
    ? `请求过于频繁，${remaining} 秒后可重试。`
    : errorMessage(error);
  return <div className="error-state" role="alert"><div><AlertTriangle size={22} aria-hidden /><strong>加载失败</strong><p>{message}</p>{retry ? <button className="button" disabled={remaining > 0} onClick={retry}>重试</button> : null}</div></div>;
}

export function Skeleton({ rows = 5 }: { rows?: number }) {
  return <div style={{ display: "grid", gap: "1rem", padding: "1.25rem" }} aria-label="正在加载">
    {Array.from({ length: rows }, (_, index) => <div className="skeleton" key={index} style={{ width: `${92 - index * 5}%` }} />)}
  </div>;
}
