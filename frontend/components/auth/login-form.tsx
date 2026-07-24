"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth/provider";
import type { UserProfile } from "@/lib/auth/types";

export function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const auth = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const next = search.get("next");
  const safeNext = next?.startsWith("/")
    && !next.startsWith("//")
    && !next.includes("\\")
    ? next
    : "/diagnosis";
  useEffect(() => {
    if (!auth.loading && auth.user) {
      router.replace(auth.user.must_change_password ? "/account/change-password" : safeNext);
    }
  }, [auth.loading, auth.user, router, safeNext]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        setError(body.error?.code === "AUTH_ACCOUNT_LOCKED" || response.status === 429
          ? "账号暂时不可用，请稍后重试"
          : response.status >= 500 ? "系统暂时不可用" : "用户名或密码错误");
        return;
      }
      const user = await response.json() as UserProfile;
      await auth.refresh();
      router.replace(user.must_change_password ? "/account/change-password" : safeNext);
    } catch {
      setError("系统暂时不可用");
    } finally {
      setBusy(false);
    }
  }
  return <form className="panel form-stack" style={{ width: "min(26rem, calc(100vw - 2rem))", padding: "1.5rem" }} onSubmit={submit}>
    <div><h1>能源诊断</h1><p className="meta">仅限获得授权的运维人员使用</p></div>
    <div className="field"><label htmlFor="username">用户名</label><input id="username" className="input" autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} /></div>
    <div className="field"><label htmlFor="password">密码</label><input id="password" className="input" type={showPassword ? "text" : "password"} autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></div>
    <label className="meta"><input type="checkbox" checked={showPassword} onChange={(event) => setShowPassword(event.target.checked)} /> 显示密码</label>
    {error ? <div className="banner danger" role="alert">{error}</div> : null}
    <button className="button primary" disabled={busy || auth.loading}>
      {auth.loading ? "正在检查会话…" : busy ? "正在登录…" : "登录"}
    </button>
  </form>;
}
