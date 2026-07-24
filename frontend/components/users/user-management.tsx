"use client";

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorMessage } from "@/lib/api/browser-client";
import type { UserProfile, UserRole } from "@/lib/auth/types";

interface UserList { items: UserProfile[]; next_cursor: string | null; has_more: boolean }
const roles: UserRole[] = ["viewer", "operator", "reviewer", "admin"];

export function UserManagement() {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<UserProfile | null>(null);
  const [adding, setAdding] = useState(false);
  const query = useInfiniteQuery({
    queryKey: ["users", q, role, status],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (role) params.set("role", role);
      if (status) params.set("status", status);
      if (pageParam) params.set("cursor", pageParam);
      return api<UserList>(`users?${params.toString()}`);
    },
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.next_cursor : undefined,
  });
  async function action(path: string, body?: object) {
    if (!selected) return;
    try {
      await api<UserProfile>(`users/${selected.user_id}/${path}`, {
        method: "POST", body: body ? JSON.stringify(body) : undefined,
      });
      setSelected(null);
      await client.invalidateQueries({ queryKey: ["users"] });
    } catch (error) { alert(errorMessage(error)); }
  }
  return <div style={{ display: "grid", gridTemplateColumns: selected || adding ? "1fr minmax(20rem, 28rem)" : "1fr", gap: "1rem" }}>
    <section className="panel">
      <div className="panel-header users-toolbar"><input className="input" placeholder="搜索用户" value={q} onChange={(e) => setQ(e.target.value)} /><select className="input" aria-label="按角色筛选" value={role} onChange={(e) => setRole(e.target.value)}><option value="">全部角色</option>{roles.map((item) => <option key={item}>{item}</option>)}</select><select className="input" aria-label="按状态筛选" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">全部状态</option><option>ACTIVE</option><option>DISABLED</option></select><button className="button primary" onClick={() => { setAdding(true); setSelected(null); }}>添加用户</button></div>
      {query.error ? <div className="banner danger">{errorMessage(query.error)}</div> : null}
      <div className="list">{query.data?.pages.flatMap((page) => page.items).map((user) => <button key={user.user_id} className="list-row" style={{ width: "100%", textAlign: "left", background: "transparent" }} onClick={() => { setSelected(user); setAdding(false); }}><div><div className="row-title">{user.display_name} <span className="meta">@{user.username}</span></div><div className="row-subtitle">{user.email ?? "无 Email"}</div></div><span className="badge">{user.role}</span><span className={`badge ${user.status === "ACTIVE" ? "complete" : "warning"}`}>{user.status}</span></button>)}</div>
      {query.hasNextPage ? <div style={{ padding: ".75rem", textAlign: "center" }}><button className="button" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>{query.isFetchingNextPage ? "正在加载…" : "加载更多"}</button></div> : null}
    </section>
    {adding ? <CreateUser onClose={() => setAdding(false)} onSaved={async () => { setAdding(false); await client.invalidateQueries({ queryKey: ["users"] }); }} /> : null}
    {selected ? <EditUser user={selected} onClose={() => setSelected(null)} onSaved={async () => { setSelected(null); await client.invalidateQueries({ queryKey: ["users"] }); }} onAction={action} /> : null}
  </div>;
}

function CreateUser({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }) {
  const [form, setForm] = useState({ username: "", display_name: "", email: "", role: "viewer" as UserRole, initial_password: "", confirm: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (form.initial_password !== form.confirm) return setError("两次输入的密码不一致");
    setBusy(true);
    setError("");
    try {
      await api<UserProfile>("users", { method: "POST", body: JSON.stringify({ ...form, email: form.email || null, confirm: undefined }) });
      await onSaved();
      alert("用户已创建，首次登录需要修改密码。");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  return <form className="panel form-stack" style={{ padding: "1rem" }} onSubmit={submit}><h2>添加用户</h2>{(["username", "display_name", "email"] as const).map((name) => <div className="field" key={name}><label>{name === "username" ? "用户名" : name === "display_name" ? "显示名称" : "Email（可选）"}</label><input className="input" required={name !== "email"} value={form[name]} onChange={(e) => setForm({ ...form, [name]: e.target.value })} /></div>)}<div className="field"><label>角色</label><select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}>{roles.map((item) => <option key={item}>{item}</option>)}</select></div><div className="field"><label>初始密码</label><input type="password" className="input" minLength={10} required value={form.initial_password} onChange={(e) => setForm({ ...form, initial_password: e.target.value })} /></div><div className="field"><label>确认初始密码</label><input type="password" className="input" required value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} /></div>{error ? <div className="banner danger">{error}</div> : null}<div><button className="button primary" disabled={busy}>{busy ? "正在创建…" : "创建"}</button> <button type="button" className="button" onClick={onClose}>取消</button></div></form>;
}

function EditUser({ user, onClose, onSaved, onAction }: { user: UserProfile; onClose: () => void; onSaved: () => Promise<void>; onAction: (path: string, body?: object) => Promise<void> }) {
  const [displayName, setDisplayName] = useState(user.display_name);
  const [email, setEmail] = useState(user.email ?? "");
  const [role, setRole] = useState(user.role);
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError("");
    try {
      await api<UserProfile>(`users/${user.user_id}`, { method: "PATCH", body: JSON.stringify({ display_name: displayName, email: email || null, role }) });
      await onSaved();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  return <aside className="panel form-stack" style={{ padding: "1rem" }}><h2>{user.display_name}</h2><div className="field"><label>用户名</label><input className="input" value={user.username} disabled /></div><div className="field"><label>显示名称</label><input className="input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} /></div><div className="field"><label>Email</label><input className="input" value={email} onChange={(e) => setEmail(e.target.value)} /></div><div className="field"><label>角色（单选）</label><select className="input" value={role} onChange={(e) => setRole(e.target.value as UserRole)}>{roles.map((item) => <option key={item}>{item}</option>)}</select></div><dl><dt>状态</dt><dd>{user.status}</dd><dt>最后登录时间</dt><dd>{user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "—"}</dd><dt>创建时间</dt><dd>{new Date(user.created_at).toLocaleString()}</dd></dl>{error ? <div className="banner danger" role="alert">{error}</div> : null}<button className="button primary" disabled={busy} onClick={() => void save()}>{busy ? "正在保存…" : "保存资料"}</button><div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}><button className="button" onClick={() => confirm("撤销该用户所有登录 Session？") && void onAction("revoke-sessions")}>撤销所有 Session</button>{user.status === "ACTIVE" ? <button className="button danger" onClick={() => confirm("禁用该用户？") && void onAction("disable")}>禁用</button> : <button className="button" onClick={() => void onAction("enable")}>启用</button>}</div><div className="field"><label>临时密码</label><input type="password" minLength={10} className="input" value={temporaryPassword} onChange={(e) => setTemporaryPassword(e.target.value)} /></div><button className="button danger" disabled={temporaryPassword.length < 10} onClick={() => confirm("重置临时密码并撤销全部 Session？") && void onAction("reset-password", { temporary_password: temporaryPassword })}>重置临时密码</button><button className="button" onClick={onClose}>关闭</button></aside>;
}
