"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/provider";

export function ChangePasswordForm() {
  const router = useRouter();
  const auth = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (next !== confirm) return setMessage("两次输入的新密码不一致");
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/auth/change-password", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        setMessage(body.error?.code === "AUTH_CURRENT_PASSWORD_INVALID"
          ? "当前密码错误"
          : response.status >= 500 ? "系统暂时不可用，请稍后重试" : "新密码不符合要求");
        return;
      }
      await auth.refresh();
      router.replace("/diagnosis");
    } catch {
      setMessage("系统暂时不可用，请稍后重试");
    } finally {
      setBusy(false);
    }
  }
  return <form className="panel form-stack" style={{ maxWidth: "34rem", padding: "1.25rem" }} onSubmit={submit}>
    <p className="meta">密码长度为 10–128 个字符，且不能与用户名相同。</p>
    <div className="field"><label htmlFor="current-password">当前密码</label><input id="current-password" type="password" className="input" required value={current} onChange={(e) => setCurrent(e.target.value)} /></div>
    <div className="field"><label htmlFor="new-password">新密码</label><input id="new-password" type="password" className="input" required minLength={10} value={next} onChange={(e) => setNext(e.target.value)} /></div>
    <div className="field"><label htmlFor="confirm-password">确认新密码</label><input id="confirm-password" type="password" className="input" required value={confirm} onChange={(e) => setConfirm(e.target.value)} /></div>
    {message ? <div className="banner danger" role="alert">{message}</div> : null}
    <button className="button primary" disabled={busy}>{busy ? "正在更新…" : "修改密码"}</button>
  </form>;
}
