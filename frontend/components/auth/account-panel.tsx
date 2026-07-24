"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth/provider";

export function AccountPanel() {
  const { user, loading, logout } = useAuth();
  if (loading) return <div className="meta">正在读取账户…</div>;
  if (!user) return <div className="banner danger">当前登录已失效。</div>;
  return <div className="panel" style={{ maxWidth: "42rem", padding: "1.25rem" }}>
    <dl><dt>用户名</dt><dd>{user.username}</dd><dt>显示名称</dt><dd>{user.display_name}</dd><dt>Email</dt><dd>{user.email ?? "未设置"}</dd><dt>角色</dt><dd><span className="badge">{user.role}</span></dd><dt>账号状态</dt><dd>{user.status}</dd><dt>最后登录时间</dt><dd>{user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "—"}</dd></dl>
    <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}><Link className="button" href="/account/change-password">修改密码</Link><button className="button" onClick={() => void logout()}>退出当前设备</button><button className="button danger" onClick={() => confirm("退出所有设备？") && void logout(true)}>退出所有设备</button></div>
  </div>;
}
