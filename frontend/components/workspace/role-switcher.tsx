"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

export function RoleSwitcher() {
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState("");
  const runtime = useQuery({ queryKey: ["runtime"], queryFn: async () => {
    const response = await fetch("/api/runtime");
    if (!response.ok) throw new Error("runtime unavailable");
    return response.json() as Promise<{ local: boolean; role: string | null }>;
  }});
  if (runtime.error) return <span role="alert">角色信息加载失败，请刷新后重试。</span>;
  if (!runtime.data?.local) return null;
  return <div><select className="input" aria-label="本地开发角色" disabled={saving} value={runtime.data.role ?? "operator"} style={{ width: "auto", minHeight: "2.25rem" }} onChange={async (event) => {
    setSaving(true);
    setFailure("");
    try {
      const response = await fetch("/api/local-role", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: event.target.value }) });
      if (!response.ok) throw new Error("role update failed");
      location.reload();
    } catch {
      setFailure("角色切换失败，请重试。");
      setSaving(false);
    }
  }}><option value="viewer">viewer</option><option value="operator">operator</option><option value="reviewer">reviewer</option><option value="admin">admin</option></select>{failure ? <span role="alert">{failure}</span> : null}</div>;
}
